# 批量转换性能优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过模板字节缓存消除 200 次重复磁盘读，并用进程池并行化 Spire PDF 转换，大幅缩短 200+ 文件批量场景的总耗时。

**Architecture:** Worker 启动时把 template.docx 读成 bytes 一次，照片单元格尺寸也只探测一次；DocxExporter 接受 bytes 参数直接用 BytesIO 构造模板，不再读磁盘。PDF 转换改为 ProcessPoolExecutor 并行，每个子进程独立加载 Spire；Worker 分两阶段：先串行生成所有 DOCX，再并行转 PDF。

**Tech Stack:** Python 3.11, PySide6, docxtpl, python-docx, spire-doc-free, concurrent.futures.ProcessPoolExecutor

---

## File Map

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `app/core/docx_exporter.py` | 修改 | `__init__` 接受 `bytes\|Path`；新增 `probe_cell_size()` 静态方法；`export()` 改用 `BytesIO`；`_get_photo_cell_size()` 改为懒探测 |
| `app/core/pdf_exporter.py` | 修改 | 新增模块级 `_spire_pdf_worker()`；新增 `export_parallel()`；顶部 import `ProcessPoolExecutor`, `as_completed` |
| `app/ui/tabs/convert_tab.py` | 修改 | Worker.run() 拆为两阶段：串行 DOCX → 并行 PDF |
| `main.py` | 修改 | 加 `multiprocessing.freeze_support()`（PyInstaller 必须） |
| `tests/test_docx_exporter.py` | 修改 | 新增对 bytes 构造器和 `probe_cell_size` 的测试 |
| `tests/test_pdf_exporter.py` | 修改 | 修复已有的枚举名错误（`PdfEngine.WPS` → `PdfEngine.WPS_CLI`）；新增 `export_parallel` 测试 |

---

## Task 1: DocxExporter — bytes 支持 + probe_cell_size()

**Files:**
- Modify: `app/core/docx_exporter.py:264-278`, `489-541`
- Modify: `tests/test_docx_exporter.py`

### 背景

`DocxExporter.__init__` 目前只接受 `Path`，`export()` 里用 `DocxTemplate(self.template_path)` 读磁盘，`_get_photo_cell_size()` 再用 `DocxDoc(self.template_path)` 读一次。200 个文件共 400 次读同一文件。

改后：`__init__` 接受 `bytes | Path`，传 `Path` 时立即 `read_bytes()` 存入 `self._template_bytes`；`export()` 和 `_get_photo_cell_size()` 均用 `BytesIO(self._template_bytes)`，不再读磁盘。新增 `probe_cell_size(template_bytes)` 静态方法，供 Worker 在循环前一次性调用。

---

- [ ] **Step 1: 写失败测试**

在 `tests/test_docx_exporter.py` 末尾追加：

```python
from app.core.docx_exporter import get_template_path


def test_docx_exporter_accepts_bytes():
    """DocxExporter 可以用 bytes 构造，不读磁盘。"""
    template_bytes = get_template_path().read_bytes()
    exporter = DocxExporter(template_bytes)
    assert exporter._template_bytes == template_bytes


def test_probe_cell_size_returns_two_int_tuple():
    """probe_cell_size 始终返回长度为 2 的 int 元组。"""
    template_bytes = get_template_path().read_bytes()
    result = DocxExporter.probe_cell_size(template_bytes)
    assert isinstance(result, tuple) and len(result) == 2
    assert all(isinstance(v, int) for v in result)


def test_injected_cell_size_bypasses_probe():
    """外部传入 cell_size 时，_get_photo_cell_size 直接返回，不重新扫描。"""
    template_bytes = get_template_path().read_bytes()
    exporter = DocxExporter(template_bytes, cell_size=(914400, 1143000))
    assert exporter._get_photo_cell_size() == (914400, 1143000)


def test_sentinel_cell_size_returns_none():
    """cell_size=(-1, -1) 表示已探测但未找到，_get_photo_cell_size 返回 None。"""
    template_bytes = get_template_path().read_bytes()
    exporter = DocxExporter(template_bytes, cell_size=(-1, -1))
    assert exporter._get_photo_cell_size() is None
```

- [ ] **Step 2: 运行确认测试失败**

```
uv run pytest tests/test_docx_exporter.py::test_docx_exporter_accepts_bytes tests/test_docx_exporter.py::test_probe_cell_size_returns_two_int_tuple tests/test_docx_exporter.py::test_injected_cell_size_bypasses_probe tests/test_docx_exporter.py::test_sentinel_cell_size_returns_none -v
```

期望：4 个测试全部 FAIL（`AttributeError` 或 `TypeError`）。

- [ ] **Step 3: 修改 `DocxExporter.__init__`**

将 `app/core/docx_exporter.py` 第 264–270 行替换为：

```python
class DocxExporter:
    def __init__(self, template: 'bytes | Path', cell_size: 'tuple[int, int] | None' = None) -> None:
        if isinstance(template, bytes):
            self._template_bytes: bytes = template
        else:
            self._template_bytes = Path(template).read_bytes()
        # cell_size=None → probe lazily on first use
        # cell_size=(w,h) → use directly (w>0 means found)
        # cell_size=(-1,-1) → probe done externally, not found
        self._photo_cell_cache: tuple[int, int] | None = cell_size
        self._xueli_shrink_text: str | None = None
        self._jianli_line_count: int = 0
        self._jianli_lines: list[str] = []
```

注意：`self.template_path` 属性已不再需要。如果其他代码（compat_tab 等）传入 `Path`，`read_bytes()` 会在构造时自动读取，行为不变。

- [ ] **Step 4: 修改 `export()` 使用 BytesIO**

将第 272–278 行：

```python
    def export(self, lrmx: LrmxFile, output_path: Path) -> None:
        tpl = DocxTemplate(self.template_path)
        context = self._build_context(lrmx, tpl)
        tpl.render(context)
        out = Path(output_path)
        tpl.save(out)
        self._post_process(out)
```

替换为：

```python
    def export(self, lrmx: LrmxFile, output_path: Path) -> None:
        tpl = DocxTemplate(BytesIO(self._template_bytes))
        context = self._build_context(lrmx, tpl)
        tpl.render(context)
        out = Path(output_path)
        tpl.save(out)
        self._post_process(out)
```

- [ ] **Step 5: 新增 `probe_cell_size()` 静态方法，修改 `_get_photo_cell_size()`**

将第 489–541 行（`_get_photo_cell_size` 整个方法）替换为：

```python
    @staticmethod
    def probe_cell_size(template_bytes: bytes) -> tuple[int, int]:
        """扫描模板，返回照片单元格 (width_emu, height_emu)。
        找不到时返回 (-1, -1)。供批量转换前一次性调用。
        """
        try:
            from docx import Document as DocxDoc
            doc = DocxDoc(BytesIO(template_bytes))
            for table in doc.tables:
                trs = table._tbl.findall(f'{{{_W}}}tr')
                for tr_idx, tr in enumerate(trs):
                    for tc in tr.findall(f'{{{_W}}}tc'):
                        if 'ZhaoPian' not in tc.xml:
                            continue
                        tc_pr = tc.find(f'{{{_W}}}tcPr')
                        vm = tc_pr.find(f'{{{_W}}}vMerge') if tc_pr is not None else None
                        if vm is not None and vm.get(f'{{{_W}}}val', '') != 'restart':
                            continue
                        cell_w = 0
                        if tc_pr is not None:
                            tc_w_el = tc_pr.find(f'{{{_W}}}tcW')
                            if tc_w_el is not None:
                                w_val = tc_w_el.get(f'{{{_W}}}w')
                                w_type = tc_w_el.get(f'{{{_W}}}type', '')
                                if w_val and w_type == 'dxa':
                                    cell_w = int(w_val) * 635
                        if cell_w == 0:
                            for row in table.rows:
                                for cell in row.cells:
                                    if cell._tc is tc and cell.width:
                                        cell_w = int(cell.width)
                                        break
                        grid_col = _grid_col_of(tr, tc)
                        total_h = _tr_height_emu(tr)
                        for next_tr in trs[tr_idx + 1:]:
                            next_tc = _tc_at_grid_col(next_tr, grid_col)
                            if next_tc is None:
                                break
                            next_pr = next_tc.find(f'{{{_W}}}tcPr')
                            next_vm = next_pr.find(f'{{{_W}}}vMerge') if next_pr is not None else None
                            if next_vm is not None and next_vm.get(f'{{{_W}}}val', '') != 'restart':
                                total_h += _tr_height_emu(next_tr)
                            else:
                                break
                        if cell_w > 0 and total_h > 0:
                            return (cell_w, total_h)
        except Exception:
            pass
        return (-1, -1)

    def _get_photo_cell_size(self) -> Optional[tuple[int, int]]:
        """返回照片单元格 (width_emu, height_emu)，找不到返回 None。"""
        if self._photo_cell_cache is not None:
            return self._photo_cell_cache if self._photo_cell_cache[0] > 0 else None
        result = DocxExporter.probe_cell_size(self._template_bytes)
        self._photo_cell_cache = result
        return result if result[0] > 0 else None
```

- [ ] **Step 6: 运行测试确认通过**

```
uv run pytest tests/test_docx_exporter.py -v
```

期望：所有测试 PASS。

- [ ] **Step 7: Commit**

```
git add app/core/docx_exporter.py tests/test_docx_exporter.py
git commit -m "perf: DocxExporter 接受 bytes，新增 probe_cell_size 静态方法"
```

---

## Task 2: PdfExporter — 模块级 worker + export_parallel()

**Files:**
- Modify: `app/core/pdf_exporter.py`
- Modify: `tests/test_pdf_exporter.py`

### 背景

`concurrent.futures.ProcessPoolExecutor` 要求 worker 函数在模块顶层定义（可 pickle），不能是 lambda 或嵌套函数。`export_parallel` 在 `PdfExporter` 上新增，用 `as_completed` 实时回报进度。

---

- [ ] **Step 1: 在 `pdf_exporter.py` 顶部追加两个 import**

在第 1 行 `import shutil` 后的 import 块末尾加：

```python
from concurrent.futures import ProcessPoolExecutor, as_completed
```

- [ ] **Step 2: 在 `pdf_exporter.py` 的 `PdfExporter` 类定义之前（约第 55 行之前）插入模块级 worker 函数**

```python
def _spire_pdf_worker(args: tuple[str, str]) -> str:
    """在子进程中运行，独立加载 Spire，将 docx 转为 pdf。
    args = (docx_path_str, output_dir_str)
    返回生成的 pdf_path_str。
    必须是模块级函数，否则无法被 multiprocessing pickle。
    """
    docx_path_str, output_dir_str = args
    from spire.doc import Document, FileFormat
    from pathlib import Path as _Path
    pdf_path = _Path(output_dir_str) / (_Path(docx_path_str).stem + '.pdf')
    doc = Document()
    doc.LoadFromFile(docx_path_str)
    doc.SaveToFile(str(pdf_path), FileFormat.PDF)
    doc.Close()
    return str(pdf_path)
```

- [ ] **Step 3: 在 `PdfExporter` 类末尾（`_via_com` 方法之后）新增 `export_parallel()`**

```python
    def export_parallel(
        self,
        jobs: 'list[tuple[Path, Path]]',
        on_progress: 'Callable[[str, str | None, str], None] | None' = None,
    ) -> None:
        """并行转换 docx → pdf。
        jobs: [(docx_path, output_dir), ...]
        on_progress(stem, pdf_path_str_or_None, error_str) 每个文件完成时回调。
        进程数 = min(cpu_count, len(jobs))，as_completed 随完成随回报。
        """
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

- [ ] **Step 4: 写测试**

用 `Callable` 需在 `pdf_exporter.py` 顶部 import：`from typing import Callable`（若尚未存在）。

在 `tests/test_pdf_exporter.py` 顶部修复已有枚举名并追加新测试：

```python
# 文件开头 import 行更新（PdfEngine.WPS → PdfEngine.WPS_CLI）：
from app.core.pdf_exporter import PdfExporter, PdfEngine, detect_engine, _spire_pdf_worker

# 修复已有损坏的测试：
def test_detect_engine_finds_wps():
    with patch('shutil.which', side_effect=lambda x: '/usr/bin/wps' if x == 'wps' else None):
        assert detect_engine() == PdfEngine.WPS_CLI   # 原来写的 PdfEngine.WPS，已不存在


# 在文件末尾追加：
def test_spire_pdf_worker_is_callable():
    """_spire_pdf_worker 是模块级可调用对象（可 pickle）。"""
    import pickle
    assert callable(_spire_pdf_worker)
    pickle.dumps(_spire_pdf_worker)   # 若不能 pickle 则 ProcessPoolExecutor 会崩


def test_export_parallel_calls_on_progress_per_job(tmp_path):
    """export_parallel 为每个 job 调用一次 on_progress。"""
    from unittest.mock import patch, MagicMock
    from concurrent.futures import Future

    def make_future(result_val):
        f = Future()
        f.set_result(result_val)
        return f

    jobs = [
        (tmp_path / 'a.docx', tmp_path),
        (tmp_path / 'b.docx', tmp_path),
    ]
    future_a = make_future(str(tmp_path / 'a.pdf'))
    future_b = make_future(str(tmp_path / 'b.pdf'))

    calls: list[tuple] = []

    mock_executor = MagicMock()
    mock_executor.submit.side_effect = [future_a, future_b]

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_executor)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch('app.core.pdf_exporter.ProcessPoolExecutor', return_value=mock_ctx):
        with patch('app.core.pdf_exporter.as_completed', return_value=[future_a, future_b]):
            PdfExporter().export_parallel(jobs, on_progress=lambda s, p, e: calls.append((s, p, e)))

    assert len(calls) == 2
    stems = {c[0] for c in calls}
    assert 'a' in stems and 'b' in stems


def test_export_parallel_handles_worker_exception(tmp_path):
    """worker 抛异常时，on_progress 收到 (stem, None, error_msg)。"""
    from unittest.mock import patch, MagicMock
    from concurrent.futures import Future

    def make_failed_future(exc):
        f = Future()
        f.set_exception(exc)
        return f

    jobs = [(tmp_path / 'bad.docx', tmp_path)]
    bad_future = make_failed_future(RuntimeError('Spire failed'))

    calls: list[tuple] = []

    mock_executor = MagicMock()
    mock_executor.submit.return_value = bad_future

    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_executor)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    with patch('app.core.pdf_exporter.ProcessPoolExecutor', return_value=mock_ctx):
        with patch('app.core.pdf_exporter.as_completed', return_value=[bad_future]):
            PdfExporter().export_parallel(jobs, on_progress=lambda s, p, e: calls.append((s, p, e)))

    assert calls == [('bad', None, 'Spire failed')]
```

- [ ] **Step 5: 运行测试**

```
uv run pytest tests/test_pdf_exporter.py -v
```

期望：所有测试 PASS。

- [ ] **Step 6: Commit**

```
git add app/core/pdf_exporter.py tests/test_pdf_exporter.py
git commit -m "perf: 新增 _spire_pdf_worker 和 export_parallel 进程池并行 PDF 转换"
```

---

## Task 3: Worker — 两阶段重构

**Files:**
- Modify: `app/ui/tabs/convert_tab.py:35-92`

### 背景

Worker.run() 目前是单循环：每个文件 docx → pdf → 下一个。改后拆两阶段：阶段一串行生成所有 DOCX（用 Task 1 的缓存），收集 pdf_jobs；阶段二调用 `export_parallel` 并行 PDF。

无自动化测试（UI 层），实现后手工跑一批文件验证。

---

- [ ] **Step 1: 在 Worker.run() 开头，替换模板加载逻辑**

将当前 `run()` 方法里的模板路径获取部分（第 39–44 行）替换为：

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
        pdf_available = False
        if self.do_pdf:
            pdf_available = pdf_exporter.available()
            if not pdf_available:
                self.log.emit('△ 未检测到可用 PDF 渲染引擎，PDF 输出已跳过')
```

- [ ] **Step 2: 替换 for 循环主体，收集 pdf_jobs**

将 `succeeded: list[bool] = [False] * total` 到 `for tmp_dir in tmp_dirs:` 之前的代码替换为：

```python
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
```

- [ ] **Step 3: 在循环之后、tmp_dirs 清理之前，插入阶段二**

```python
        # ── 阶段二：并行 PDF ─────────────────────────────────────────
        if pdf_jobs:
            pdf_total = len(pdf_jobs)
            pdf_done_count = [0]

            def _on_pdf(stem: str, pdf_path: 'str | None', err: str) -> None:
                pdf_done_count[0] += 1
                n = f'({pdf_done_count[0]}/{pdf_total})'
                if err:
                    self.log.emit(f'✗ {stem}: {err} {n}')
                else:
                    self.log.emit(f'✓ {stem} → pdf 完成 {n}')

            pdf_exporter.export_parallel(pdf_jobs, on_progress=_on_pdf)
```

- [ ] **Step 4: 确认收尾代码不变**

循环和阶段二之后应保持：

```python
        for tmp_dir in tmp_dirs:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        done = sum(succeeded)
        self.finished.emit(done, total, time.monotonic() - start)
```

- [ ] **Step 5: 手工验证**

启动应用：
```
uv run python -m app
```

选 5 个以上 lrmx 文件，勾选 docx + pdf，点开始转换。

预期日志顺序：
1. 连续出现所有 `✓ 姓名 → docx 完成 (x/N)`
2. 随后并行乱序出现 `✓ 姓名 → pdf 完成 (x/N)`（顺序不定，但计数正确）
3. 最后出现 `完成 N/N，耗时 Xs`

- [ ] **Step 6: Commit**

```
git add app/ui/tabs/convert_tab.py
git commit -m "perf: Worker 拆两阶段，串行 DOCX + 进程池并行 PDF"
```

---

## Task 4: main.py — freeze_support

**Files:**
- Modify: `main.py:13-15`

### 背景

PyInstaller 在 Windows 上用 `spawn` 启动 `ProcessPoolExecutor` 子进程时，会重新执行打包后的可执行文件入口。`multiprocessing.freeze_support()` 检测到这种情况后正确处理并退出，**缺少此调用时打包版会无限生成子进程直到崩溃**。开发环境下此调用是无操作，不影响正常运行。

---

- [ ] **Step 1: 修改 `main.py`**

将当前：

```python
if __name__ == '__main__':
    main()
```

替换为：

```python
if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
```

- [ ] **Step 2: 验证开发环境不受影响**

```
uv run python -m app
```

应正常启动，无任何报错或额外输出。

- [ ] **Step 3: Commit**

```
git add main.py
git commit -m "fix: 加 freeze_support，防止 PyInstaller 打包版启动进程池时无限自我复制"
```

---

## Self-Review

**Spec coverage:**
- ✅ DocxExporter bytes 支持 → Task 1
- ✅ probe_cell_size 静态方法 → Task 1
- ✅ _spire_pdf_worker 模块级函数 → Task 2
- ✅ export_parallel 方法 → Task 2
- ✅ Worker 两阶段重构 → Task 3
- ✅ freeze_support → Task 4

**Placeholder scan:** 无 TBD / TODO / "add appropriate error handling" 等模糊描述。

**Type consistency:**
- `probe_cell_size` 返回 `tuple[int, int]`（含 (-1,-1) 哨兵），与 Task 3 中 `DocxExporter(template_bytes, cell_size)` 调用一致
- `export_parallel` 接受 `list[tuple[Path, Path]]`，Task 3 中 `pdf_jobs: list[tuple[Path, Path]]` 类型一致
- `on_progress(stem: str, pdf_path_str_or_None, error_str)` 签名在 Task 2 定义，Task 3 的 `_on_pdf` 函数与之一致
