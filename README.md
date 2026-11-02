# xianyu-customer-service-agent
An AI customer service agent for Xianyu, built with Python, FastAPI, and LLMs.

本机命令使用 `python`（Python 3.11）。没有 `py` 或 `python3` 命令。

## 安装与测试

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest
```

如果执行策略允许，也可以先运行 `.\.venv\Scripts\Activate.ps1`，之后把上面的解释器换成 `python`。

测试不会打开 Chrome，也不会访问 DeepSeek。自动回复只在真正启动服务时运行。

## 启动

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

默认端口是 8000。本机 8000 已被别的程序占用，所以用 8011。

- 健康检查：<http://127.0.0.1:8011/health>，返回 `{"status":"ok"}`
- 客服页：<http://127.0.0.1:8011/>
- 接口说明：<http://127.0.0.1:8011/docs>

复制 `.env.example` 为 `.env` 后，在本机填写 `DEEPSEEK_API_KEY` 和 `WECHAT_ID`。没有密钥时用模板生成。`.env`、数据库和 `browser-profile/` 都不会提交。

## 闲鱼网页自动回复

服务启动后会盯着已经登录的闲鱼网页。它通过本机 Chrome 或 Edge 的调试端口操作 [https://www.goofish.com/im](https://www.goofish.com/im)，读到买家的新消息后直接填进输入框并点击发送。不走闲鱼私信接口，也不把 Cookie 读进仓库。

1. 本机需要已安装 Chrome 或 Edge。调试端口没开时，程序会用项目里的 `browser-profile/` 打开一个窗口。
2. 在那个窗口打开 [https://www.goofish.com/](https://www.goofish.com/) 自己登录。不要把登录信息交给仓库。
3. 登录成功后不要关掉这个窗口。停掉服务不会关闭它。
4. 客服页顶部会显示是否已经连上。打招呼、问在不在和问价格会立刻按规则回复；其他问题交给 DeepSeek 写一句短回复。

同一句话如果买家又发了一次，会再回一次。手动测试步骤见 [docs/xianyu-readonly.md](docs/xianyu-readonly.md)。

## 回复规则

当前演示服务是代码复现、机器学习、深度学习训练和 Python 脚本。价格、交付内容、周期和最低价只来自 `data/products.json` 里的虚构资料。

- 回复用口语，通常一句，最多两句。
- 问价格、优惠或出价时不报金额，只给出 `.env` 里的微信号。
- 买家没问技术、也没指定技术时，不主动说技术栈。买家指定了就按买家的技术来。
- 退款、辱骂、站外转账，以及包过、代写论文、代考、保分或替交，不答应。答应这些的句子会在发送前改成拒绝。

## 模块

- `app/main.py`：应用入口。直接运行时会启动自动回复
- `app/api/`：草稿、商品、会话，以及闲鱼状态和粘贴导入
- `app/services/draft.py`：把检索、生成、风险和会话串起来
- `app/services/auto_reply.py`：后台盯着闲鱼网页
- `app/services/risk.py`：退款、站外交易、辱骂和资料中没有的承诺
- `app/connectors/live_reply.py`：通过浏览器调试端口读取并发送
- `app/connectors/xianyu.py`：粘贴对话
- `app/knowledge/store.py`：读取虚构商品
- `app/llm/`：模板生成器和 DeepSeek 客户端
- `app/memory/store.py`：SQLite 会话，以及已经回复过的那一轮
- `app/static/index.html`：客服操作页
