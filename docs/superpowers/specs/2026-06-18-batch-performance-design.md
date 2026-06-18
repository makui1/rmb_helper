# 批量转换性能优化 Implementation Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 针对 200+ 文件批量场景，通过模板字节缓存消除重复磁盘读，并用进程池并行化 Spire PDF 转换，大幅缩短总耗时。

**Background:** 用户典型批量量级为 200+ 个 lrmx 文件，同时选择 docx + pdf 输出。当前两个主要瓶颈：
1. 每个文件独立读两次 `template.docx`（DocxTemplate + DocxDoc），200 文件 = 400 次重复磁盘读
2. Spire PDF 转换完全串行，多核 CPU 完全闲置

---

## Architecture

三个改动点，互相独立，可分 Task 实施：

```
convert_tab.Worker.run()
  ├─ [新] 启动时读 template_bytes（1次磁盘读）
  ├─ [新] 启动时探测 photo_cell_size（1次模板扫描）
  ├─ 阶段一：串行 DOCX 循环（用缓存数据，不读磁盘）
  │     └─ DocxExporter(template_bytes, cell_size).export()
  └─ 阶段二：并行 PDF
        └─ PdfExporter.export_parallel(pdf_jobs, on_progress)
              └─ ProcessPoolExecutor → _spire_pdf_worker()（模块级）
```

---

## Section 1: DocxExporter 模板缓存

**文件：** `app/core/docx_exporter.py`

### 接口变更

`DocxExporter.__init__` 改为接受 `bytes | Path`：

```python
def __init__(self, template: 'bytes | Path', cell_size: 'tuple[int,int] | None' = None) -> None:
    if isinstance(template, bytes):
        self._template_bytes: bytes = template
        self.template_path: Path | None = None
    else:
        self.template_path = Path(template)
        self._template_bytes = self.template_path.read_bytes()
    # 若外部已探测，直接注入，跳过 _get_photo_cell_size() 的模板扫描
    self._photo_cell_cache: tuple[int, int] | None = cell_size if cell_size else None
    self._xueli_shrink_text: str | None = None
    self._jianli_line_count: int = 0
    self._jianli_lines: list[str] = []
```

`export()` 内部改为：

```python
tpl = DocxTemplate(BytesIO(self._template_bytes))
```

### 新增静态方法

```python
@staticmethod
def probe_cell_size(template_bytes: bytes) -> 'tuple[int, int] | None':
    """扫描模板，返回照片单元格 (width_emu, height_emu)，供批量前一次性调用。"""
    # 将原 _get_photo_cell_size() 中的扫描逻辑提取至此
    # 入参改为 BytesIO(template_bytes) 而非磁盘路径
```

### 向后兼容

传 `Path` 时行为不变（内部立即 `read_bytes()`），compat_tab 等其他调用方无需修改。

---

## Section 2: 进程池 PDF

**文件：** `app/core/pdf_exporter.py`

### 模块级 worker 函数

必须是模块级函数，才能被 `multiprocessing` pickle：

```python
def _spire_pdf_worker(args: tuple[str, str]) -> str:
    """
    在子进程中运行，独立加载 Spire。
    args = (docx_path_str, output_dir_str)
    返回生成的 pdf_path_str。
    """
    docx_path, output_dir = args
    from spire.doc import Document, FileFormat
    from pathlib import Path
    pdf_path = Path(output_dir) / (Path(docx_path).stem + '.pdf')
    doc = Document()
    doc.LoadFromFile(str(docx_path))
    doc.SaveToFile(str(pdf_path), FileFormat.PDF)
    doc.Close()
    return str(pdf_path)
```

### PdfExporter.export_parallel()

```python
def export_parallel(
    self,
    jobs: 'list[tuple[Path, Path]]',
    on_progress: 'Callable[[str, str | None, str], None] | None' = None,
) -> None:
    """
    jobs: [(docx_path, output_dir), ...]
    on_progress(stem, pdf_path_str_or_None, error_str) 每个文件完成时回调。
    使用 cpu_count() 个子进程并行，as_completed() 实时回报。
    """
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import os
    n = min(os.cpu_count() or 1, len(jobs))
    str_jobs = [(str(d), str(o)) for d, o in jobs]
    with ProcessPoolExecutor(max_workers=n) as executor:
        future_to_stem = {
            executor.submit(_spire_pdf_worker, job): Path(job[0]).stem
            for job in str_jobs
        }
        for future in as_completed(future_to_stem):
            stem = future_to_stem[future]
            try:
                pdf_path = future.result()
                if on_progress:
                    on_progress(stem, pdf_path, '')
            except Exception as e:
                if on_progress:
                    on_progress(stem, None, str(e))
```

---

## Section 3: Worker 协调逻辑

**文件：** `app/ui/tabs/convert_tab.py`

### Worker.run() 两阶段结构

```python
def run(self):
    start = time.monotonic()
    total = len(self.files)

    # ── 模板准备（各一次） ────────────────────────────────────────
    try:
        template_bytes = get_template_path().read_bytes()
    except FileNotFoundError as e:
        self.log.emit(f'✗ {e}')
        self.finished.emit(0, total, 0.0)
        return

    cell_size = DocxExporter.probe_cell_size(template_bytes)

    pdf_exporter = PdfExporter()
    pdf_available = self.do_pdf and pdf_exporter.available()
    if self.do_pdf and not pdf_available:
        self.log.emit('△ 未检测到可用 PDF 渲染引擎，PDF 输出已跳过')

    # ── 阶段一：串行生成 DOCX ────────────────────────────────────
    succeeded: list[bool] = [False] * total
    pdf_jobs: list[tuple[Path, Path]] = []   # (docx_path, output_dir)
    tmp_dirs: set[Path] = set()

    for idx, lrmx_path in enumerate(self.files):
        num = f'({idx + 1}/{total})'
        try:
            lf = LrmxFile(Path(lrmx_path))
            stem = apply_rule(self.naming_rule, lf.as_dict()) or Path(lrmx_path).stem
            out_dir = Path(lrmx_path).parent if self.sibling_dir else self.output_dir

            if self.do_docx:
                docx_path = out_dir / (stem + '.docx')
                DocxExporter(template_bytes, cell_size).export(lf, docx_path)
                self.log.emit(f'✓ {stem} → docx 完成 {num}')
                if pdf_available:
                    pdf_jobs.append((docx_path, out_dir))
                succeeded[idx] = True

            elif pdf_available:
                tmp_dir = out_dir / '.tmp_docx'
                tmp_dirs.add(tmp_dir)
                tmp_dir.mkdir(parents=True, exist_ok=True)
                tmp_docx = tmp_dir / (stem + '.docx')
                DocxExporter(template_bytes, cell_size).export(lf, tmp_docx)
                pdf_jobs.append((tmp_docx, out_dir))
                succeeded[idx] = True

            else:
                succeeded[idx] = True

        except Exception as e:
            self.log.emit(f'✗ {Path(lrmx_path).name}: {e} {num}')

    # ── 阶段二：并行 PDF ─────────────────────────────────────────
    if pdf_jobs:
        pdf_total = len(pdf_jobs)
        pdf_done_count = [0]

        def _on_pdf(stem, pdf_path, err):
            pdf_done_count[0] += 1
            num = f'({pdf_done_count[0]}/{pdf_total})'
            if err:
                self.log.emit(f'✗ {stem}: {err} {num}')
            else:
                self.log.emit(f'✓ {stem} → pdf 完成 {num}')

        pdf_exporter.export_parallel(pdf_jobs, on_progress=_on_pdf)

    # ── 收尾 ────────────────────────────────────────────────────
    for tmp_dir in tmp_dirs:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    done = sum(succeeded)
    self.finished.emit(done, total, time.monotonic() - start)
```

### 注意：succeeded 与 pdf 失败

阶段一 `succeeded[idx] = True` 仅代表 DOCX 成功。PDF 阶段的失败单独记日志，不影响 `done` 计数（与现有行为一致）。

---

## Section 4: main.py freeze_support

**文件：** `main.py`

PyInstaller 打包后，Windows 上 `multiprocessing` 用 spawn 启动子进程时会重新执行可执行文件入口。`freeze_support()` 负责检测此情况并正确处理，**缺少此调用打包版会无限生成子进程并崩溃**。

```python
if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
```

---

## Files Changed

| 文件 | 改动类型 |
|------|---------|
| `app/core/docx_exporter.py` | 修改 `__init__`；提取 `probe_cell_size()` 静态方法；`export()` 改用 `BytesIO` |
| `app/core/pdf_exporter.py` | 新增模块级 `_spire_pdf_worker()`；新增 `export_parallel()` |
| `app/ui/tabs/convert_tab.py` | Worker.run() 拆两阶段；循环前缓存模板和尺寸 |
| `main.py` | 加 `freeze_support()` |

不涉及：`compat_tab.py`、`verify_tab.py`、`settings_tab.py`、UI 结构、QSS。

---

## Expected Improvement

| 环节 | 改前 | 改后 |
|------|------|------|
| 模板磁盘读次数（200文件）| 400次 | 1次 |
| PDF 并发度 | 1 | cpu_count()（8核机器约8倍） |
| 用户可见进度 | 串行逐条 | docx 阶段串行完，pdf 阶段并行刷 |
