# 干部任免审批表工具箱

> 批量处理 `.lrmx` 格式干部任免审批表的 Windows 桌面工具，支持格式转换、版本兼容与数据核验/更新。

---

## 功能介绍

### 📄 批量格式转换
将 `.lrmx` 文件批量导出为 Word（`.docx`）或 PDF 格式。

- 自定义文件命名规则，支持姓名、职务、日期等字段自由组合
- 可输出到指定目录，或与源文件放在同一目录
- 实时显示转换进度与日志，完成后一键打开输出目录

### 🔄 批量版本兼容
将旧版 `.lrmx` 文件批量升级为当前版本格式，字段内容完整保留。

### ✅ 批量核验 / 更新
以 Excel 表格为数据源，对 `.lrmx` 文件进行逐字段比对与批量回写。

- 支持**精确匹配**与**模糊匹配**两种人员识别模式
- 差异内容高亮对比展示，可逐项确认后再写入
- 核验结果支持导出为 Excel 或 HTML 报告
- 字段映射完全自定义，支持别名识别

---

## 界面特性

- 自定义无边框窗口，支持拖拽移动与边缘调整大小
- 左侧导航栏可折叠，最大化工作区域
- 全局共享文件面板，支持拖放文件/文件夹，可递归扫描子目录
- 文件面板宽度自适应：窗口较窄时工具栏按钮自动切换为纯图标模式

---

## 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10 / 11 |
| Python | ≥ 3.12 |
| 包管理器 | [uv](https://github.com/astral-sh/uv) |

---

## 安装与运行

```bash
# 1. 克隆仓库
git clone <仓库地址>
cd rmb_helper

# 2. 安装依赖（uv 会自动创建虚拟环境）
uv sync

# 3. 启动应用
uv run python -m app
```

---

## 打包为可执行文件

```bash
uv run pyinstaller rmb_tool.spec
```

打包产物位于 `dist/` 目录下。

---

## 项目结构

```
rmb_helper/
├── app/
│   ├── core/                   # 核心业务逻辑
│   │   ├── lrmx.py             # .lrmx 文件读写
│   │   ├── docx_exporter.py    # Word 导出
│   │   ├── pdf_exporter.py     # PDF 导出
│   │   ├── excel_handler.py    # Excel 读取与回写
│   │   ├── verify_handler.py   # 核验逻辑
│   │   └── result_exporter.py  # 核验结果导出
│   ├── ui/
│   │   ├── main_window.py      # 主窗口
│   │   ├── style.py            # 全局样式（QSS）
│   │   ├── tabs/               # 各功能标签页
│   │   └── widgets/            # 共享组件（文件面板等）
│   └── utils/
│       └── naming.py           # 文件命名规则
└── tests/                      # 单元测试
```

---

## 开发

```bash
# 运行测试
uv run pytest
```
