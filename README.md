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

## 启动

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

- 健康检查：<http://127.0.0.1:8000/health>，返回 `{"status":"ok"}`
- 客服页：<http://127.0.0.1:8000/>
- 接口说明：<http://127.0.0.1:8000/docs>

复制 `.env.example` 为 `.env` 后，可以在本机填写 `DEEPSEEK_API_KEY`。没有密钥时，草稿使用模板生成，测试也不会访问 DeepSeek。

## 模块

- `app/main.py`：应用入口、健康检查和客服页
- `app/api/`：草稿、商品、会话和闲鱼粘贴接口
- `app/services/draft.py`：把检索、生成、风险和会话串起来
- `app/services/risk.py`：退款、站外交易、辱骂和资料中没有的承诺
- `app/knowledge/store.py`：读取 `data/products.json` 里的虚构商品
- `app/llm/`：模板生成器和 DeepSeek 客户端
- `app/memory/store.py`：SQLite 会话
- `app/static/index.html`：客服操作页
- `app/connectors/xianyu.py`：粘贴对话；浏览器读取默认关闭

当前演示服务是论文代码复现、机器学习、深度学习训练和 Python 脚本。价格、交付内容、技术栈、周期和最低价只来自虚构资料。客服会回答接单、报价、交付内容、技术栈、周期和砍价。退款、辱骂、站外交易、低于最低价，以及包过、代写论文或替交，会标成人工审核。同一会话的下一句会记住上一项服务。页面只生成可复制的草稿，不发送闲鱼消息。真实页面的手动步骤见 [docs/xianyu-readonly.md](docs/xianyu-readonly.md)。
