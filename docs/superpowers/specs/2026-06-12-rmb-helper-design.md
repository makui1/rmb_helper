# 干部任免审批表管理工具 设计文档

**日期：** 2026-06-12  
**项目：** rmb_helper  
**状态：** 已确认，待实现

---

## 一、项目背景

组织工作者日常处理大量 `.lrmx` 格式的干部任免审批表文件。`.lrmx` 是 XML 格式，包含干部基本信息、简历、家庭成员、职务等40余个字段。现有软件操作繁琐，缺乏批量处理能力。

本工具提供一个桌面 GUI，覆盖最常见的批量操作需求。

---

## 二、MVP 功能范围

本期实现以下三个功能，其余功能后续迭代：

| 功能 | 说明 |
|------|------|
| lrmx → docx | 批量将 lrmx 文件填充进 Word 模板，输出 .docx |
| lrmx → pdf | 批量将 lrmx 文件转换为 PDF（排版忠于模板） |
| Excel 批量更新 lrmx | 读取 Excel 汇总表，按匹配依据找到对应 lrmx 文件，更新指定字段 |

**已设计但暂不实现的功能（后续 Tab 扩展）：**
- lrmx 照片提取
- lrmx 规范化（去除多余空格等）
- 汇总表 → lrmx（Excel 生成 lrmx 文件）
- lrmx 兼容性处理（3.0 → 4.0）
- lrmx → 干部信息汇总表（可选字段导出 Excel）

---

## 三、整体架构

### 目录结构

```
rmb_helper/
├── main.py                        # 入口，启动 QApplication
├── app/
│   ├── ui/
│   │   ├── main_window.py         # MainWindow + QTabWidget
│   │   └── tabs/
│   │       ├── convert_tab.py     # Tab1：转换导出
│   │       ├── update_tab.py      # Tab2：批量更新
│   │       └── settings_tab.py   # Tab3：设置
│   ├── core/                      # 纯业务逻辑，不依赖 PySide6
│   │   ├── lrmx.py                # lrmx XML 读写，LrmxFile 类
│   │   ├── docx_exporter.py       # 填充 docx 模板
│   │   ├── pdf_exporter.py        # docx → pdf，多引擎检测
│   │   └── excel_handler.py       # 读 Excel、匹配、更新 lrmx
│   └── utils/
│       └── naming.py              # 文件命名规则引擎
├── docs/
│   └── superpowers/specs/
│       └── 2026-06-12-rmb-helper-design.md
└── pyproject.toml
```

### 分层原则

- `core/` 完全不依赖 PySide6，可独立单元测试
- `ui/` 只调用 `core/`，不包含业务判断
- 后续新功能：新增 Tab + 对应 core 模块，不修改现有代码

---

## 四、UI 布局

### 主窗口

```
┌─────────────────────────────────────────────┐
│  干部任免审批表管理工具                          │
├──────────┬──────────┬──────────┬────────────┤
│ 转换导出  │ 批量更新  │  设置    │            │
├──────────┴──────────┴──────────┴────────────┤
│  [Tab 内容区]                                │
└─────────────────────────────────────────────┘
```

### Tab1 —— 转换导出

```
┌─────────────────────────────────────────────┐
│ 选择文件  [拖放或点击选择 .lrmx 文件]  [清空]  │
│ ┌─────────────────────────────────────────┐ │
│ │ 文件列表（可多选删除）                    │ │
│ └─────────────────────────────────────────┘ │
│ 输出格式  ☑ docx  ☑ pdf                     │
│ 输出目录  [路径输入框]           [浏览]       │
│ 命名规则  [预设下拉▼] / [自定义输入]          │
│                              [开始转换]       │
│ ┌─────────────────────────────────────────┐ │
│ │ 进度日志（实时滚动）                      │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

### Tab2 —— 批量更新

```
┌─────────────────────────────────────────────┐
│ lrmx 目录  [路径输入框]             [浏览]   │
│ Excel 文件 [路径输入框]             [浏览]   │
│ 匹配依据   ○ 姓名  ○ 身份证号  ○ 姓名+身份证 │
│ 更新字段   [字段多选列表，勾选要更新的字段]   │
│                              [开始更新]       │
│ ┌─────────────────────────────────────────┐ │
│ │ 进度日志（实时滚动）                      │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

### Tab3 —— 设置

```
┌─────────────────────────────────────────────┐
│ docx 模板路径  [路径输入框]        [浏览]    │
│ 命名规则预设                                  │
│   预设1: {姓名}{身份证号}   [编辑] [删除]    │
│   预设2: {姓名}_{职务}      [编辑] [删除]    │
│                             [新增预设]  [保存] │
└─────────────────────────────────────────────┘
```

---

## 五、核心技术方案

### 5.1 lrmx 解析（`core/lrmx.py`）

- 使用 `xml.etree.ElementTree` 读写
- 封装为 `LrmxFile` 类，提供 `get(field)` / `set(field, value)` / `save()` 接口
- 字段名使用 lrmx 原始 XML 标签名（拼音形式，如 `XingMing`、`ShenFenZheng`）

### 5.2 lrmx → docx（`core/docx_exporter.py`）

- 使用 `docxtpl`（基于 Jinja2）渲染模板
- 用户需一次性将模板 `.doc` 另存为 `.docx`，并在空白单元格中填入占位符，格式如 `{{XingMing}}`
- 提供字段名与占位符的对照参考文档（或在设置 Tab 显示可用字段列表）

### 5.3 lrmx → pdf（`core/pdf_exporter.py`）

流程：lrmx → 填充模板 → 临时 `.docx` → 调用渲染引擎 → `.pdf`

**渲染引擎检测顺序（程序启动时自动检测，结果缓存）：**

| 优先级 | 引擎 | 命令 | 适用环境 |
|--------|------|------|----------|
| 1 | LibreOffice | `libreoffice --headless --convert-to pdf` | 国产 Linux、部分 Windows |
| 2 | WPS Office | `wps --headless --convert-to pdf` | 国产 Linux、Windows |
| 3 | Microsoft Word | Windows COM 自动化 | Windows + Office |
| 4 | 无可用引擎 | 仅输出 docx，日志提示安装 LibreOffice 或 WPS | 降级处理 |

排版完全忠于 `.docx` 模板，不做自定义渲染。

### 5.4 Excel 批量更新（`core/excel_handler.py`）

- 使用 `openpyxl` 读取 Excel
- 匹配依据优先级：身份证号（唯一，最可靠）> 姓名+身份证号 > 姓名
- 匹配成功后，用 `LrmxFile.set()` 更新指定字段
- **写入前自动备份**：原文件重命名为 `原文件名.bak`，再写入新文件
- 匹配失败的行记录到日志，不中断整体流程

### 5.5 文件命名规则（`utils/naming.py`）

- 支持 `{字段名}` 占位符，如 `{XingMing}_{ShenFenZheng}`
- 内置预设（可在设置中增删编辑）：
  - `{XingMing}{ShenFenZheng}`（默认，与原文件名一致）
  - `{XingMing}_{XianRenZhiWu}`
- 对文件名非法字符自动替换为下划线

### 5.6 后台执行与日志

- 每次操作创建一个 `QThread`
- 通过 `pyqtSignal(str)` 将日志行实时发送到 UI 线程
- 日志框（`QPlainTextEdit`，只读）自动滚动到底部
- 操作期间「开始」按钮变灰，完成后恢复

### 5.7 设置持久化

- 使用 `QSettings`（平台原生存储）
- 存储内容：模板路径、命名规则预设列表、上次使用的输出目录

---

## 六、依赖变更

在现有依赖基础上新增：

| 新增依赖 | 用途 |
|----------|------|
| `docxtpl` | Jinja2 模板渲染，填充 docx |
| `openpyxl` | 读写 Excel 文件 |

PDF 转换依赖系统已安装的 LibreOffice / WPS / Word，不引入额外 Python 包。

---

## 七、模板准备说明（用户操作，一次性）

1. 将 `A4.doc` 在 Word/WPS 中另存为 `A4.docx`
2. 在表单对应空白单元格中填入占位符，例如：
   - 姓名对应格填 `{{XingMing}}`
   - 性别对应格填 `{{XingBie}}`
   - 身份证号对应格填 `{{ShenFenZheng}}`
   - …（完整字段列表见附录）
3. 保存，在设置 Tab 中指定该文件路径

---

## 附录：lrmx 主要字段对照

| XML 标签 | 中文含义 |
|----------|----------|
| `XingMing` | 姓名 |
| `XingBie` | 性别 |
| `ChuShengNianYue` | 出生年月 |
| `MinZu` | 民族 |
| `JiGuan` | 籍贯 |
| `ChuShengDi` | 出生地 |
| `RuDangShiJian` | 入党时间 |
| `CanJiaGongZuoShiJian` | 参加工作时间 |
| `JianKangZhuangKuang` | 健康状况 |
| `ZhengZhiMianMao` | 政治面貌 |
| `ShenFenZheng` | 身份证号 |
| `QuanRiZhiJiaoYu_XueLi` | 全日制教育学历 |
| `QuanRiZhiJiaoYu_XueWei` | 全日制教育学位 |
| `ZaiZhiJiaoYu_XueLi` | 在职教育学历 |
| `ZaiZhiJiaoYu_XueWei` | 在职教育学位 |
| `ZhuanYeJiShuZhiWu` | 专业技术职务 |
| `ShuXiZhuanYeYouHeZhuanChang` | 熟悉专业有何专长 |
| `XianRenZhiWu` | 现任职务 |
| `NiRenZhiWu` | 拟任职务 |
| `NiMianZhiWu` | 拟免职务 |
| `RenMianLiYou` | 任免理由 |
| `JianLi` | 简历 |
| `JiaTingChengYuan` | 家庭成员 |
| `NianDuKaoHeJieGuo` | 年度考核结果 |
| `JiangChengQingKuang` | 奖惩情况 |
| `ZhaoPian` | 照片（Base64） |
| `TianBiaoRen` | 填表人 |
| `TianBiaoShiJian` | 填表时间 |
