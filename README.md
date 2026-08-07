# 智谱识图（Zhipu Vision）

一句话：**让你的 AI 能"看图"**。

你用的模型如果看不了图片（比如 DeepSeek），这个工具会把图片交给智谱的免费视觉模型，再把图里有什么用文字讲给你听。

## 怎么用？一共三步

**第一步：把工具放进 Codex**

省事版：把仓库链接 **https://github.com/Zhangmu-XL/zhipu-vision** 直接发给你的 AI（比如 Codex），跟它说"帮我安装这个 skill"，它会自己下载并放好，你什么都不用做。

手动版：下载或克隆这个仓库，把里面的 `zhipu-vision` 文件夹，整个复制到：

```
C:\Users\你的用户名\.codex\skills\
```

（Mac / Linux 是 `~/.codex/skills/`。如果 `skills` 文件夹不存在，自己新建一个。）

**第二步：填上你的 Key**

进到 `zhipu-vision` 文件夹，双击 `setup.cmd`（Mac / Linux 就运行 `python3 setup.py`）。

会弹出一个黑色窗口，让你粘贴 Key。粘贴、回车，看到"已写入"就成功了。

**第三步：重启 Codex，开个新会话**

然后直接说：

> 帮我看一下 `D:\照片.jpg`

完事。压缩图片、读 RAW、认字，这些工具自己会处理，你不用管。

## 仓库里都有什么？

新手只需要碰两个文件：

- `scripts\analyze_image.cmd` —— 看图就靠它（Windows 入口）
- `scripts\setup.cmd` —— 填 Key 就靠它

其他基本不用管：

- `SKILL.md` —— 给 Codex 看的说明书，你不用打开
- `scripts\analyze_image.py` —— 核心代码本体，别碰
- `scripts\setup.py` —— Mac / Linux 版填 Key 用的
- `scripts\mcp_server.py` —— 接 Claude、Cursor 等其他 AI 用的，不接就不用管
- `references\usage.md` —— 详细说明书（参数、报错处理），遇到问题再翻
- `agents\openai.yaml` —— Codex 界面里显示的名字和简介
- `.env.example`、`.gitignore`、`requirements-mcp.txt` —— 配置和保护用的，不用管

仓库最外面还有 `README.md`（你正在看的教程）和 `LICENSE`（开源声明），也不用管。

## Key 从哪来？

1. 打开 https://open.bigmodel.cn，注册账号（免费）
2. 按要求实名认证
3. 进 **API Keys**，点创建，复制那串 Key

Key 是你的"门票"，别发给别人，也别贴到公开的地方。

## 电脑没装 Python 怎么办？

Windows 去 https://www.python.org/downloads/ 下载安装，安装时**一定勾选 "Add Python to PATH"**，装完重启一下终端。

用 Codex 桌面版的话其实不用装——工具会自动找到 Codex 自带的 Python。

## 想自己敲命令行？

Windows 打开终端，进到工具文件夹：

```
scripts\analyze_image.cmd "D:\照片.jpg" "图里有什么？"
```

Mac / Linux：

```
python3 scripts/analyze_image.py "照片.jpg" "图里有什么？"
```

引号里那句问话随便换："提取图里所有文字""这是什么 App""描述一下这张图"，都行。

## 常见问题

**没反应 / 窗口一闪而过**：多半是 Python 没装好，回上面"没装 Python"那节看看。

**提示 Key 不对（401）**：回 open.bigmodel.cn 重新复制一次，粘贴时别带上空格。

**图太大、或者相机拍的 RAW 原片**：不用管，直接传，工具会自动压缩和提取。

**回答里有些话像是猜的**：正常，模型偶尔会脑补。重要的细节（颜色、文字、数字）自己再核对一眼。

## 给会玩的人（进阶）

- 想接进 Claude Desktop / Cursor 等：运行 `scripts\mcp_server.py`，配置方法在 `zhipu-vision\references\usage.md` 里
- 想看模型"怎么想的"：命令后面加 `--show-reasoning`
- 想核对颜色和布局：加 `--pixel-check`
- 所有参数、缓存说明、完整排障表：都在 `zhipu-vision\references\usage.md`

## License

MIT
