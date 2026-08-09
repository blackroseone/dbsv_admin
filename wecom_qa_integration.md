# 企业微信接入 DBSV Admin 知识问答接口

> 面向"另一套系统的开发者或 LLM"的接入文档。目标：让阅读者能正确写出调用本项目**知识问答接口**的代码，用于企业微信（或任何外部系统）接入问答。

---

## 一、概述

DBSV Admin 是一个数据库运维平台，内置"知识问答"模块：基于 LLM + 知识库 RAG + 集群拓扑增强回答数据库问题。

**企业微信接入方式**：企微后台收到用户消息 → 调用本项目的知识问答 HTTP 接口 → 把回答返回给用户。

**关键约定**：
- 每次问答 = **单独一次 HTTP 请求**（推荐用非流式接口，拿到完整回答再回复，不要用 SSE）。
- **默认开启知识库增强和集群拓扑增强**（即 `use_rag=true`、`use_topology=true`）。

---

## 二、前置条件

1. **服务已运行**，接口地址为：`http://<服务器IP>:9163`（示例：`http://10.126.77.37:9163`）
2. **已配置大模型 LLM**：在 Web 界面「系统配置 → API 配置」填写内网 LLM 的 `api_url`、`api_key`、`model`，并"测试连接"通过。
   - 非流式接口 `/api/qa/ask` 使用**默认模型**。
   - 若未配置 LLM，接口会返回 `500`，`error` 为相关提示。
3. **当前接口无鉴权**（内网部署，无登录/token 墙）。若暴露到不可信网络，接入方需自行加访问控制（如网关限流/IP 白名单）。

---

## 三、核心接口（推荐）：`POST /api/qa/ask`

### 3.1 请求

```
POST http://<服务器IP>:9163/api/qa/ask
Content-Type: application/json
```

请求体（JSON）：

| 字段 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `question` | string | ✅ | - | 用户的问题文本 |
| `db_type` | string | ❌ | `""` | 数据库类型 id。`"auto"` = 自动识别；`""` = 不指定类型（通用回答）；也可指定如 `"mysql"`、`"oracle"`、`"dm"` |
| `use_rag` | bool | ❌ | `true` | 知识库增强（RAG，注入检索到的知识库上下文） |
| `use_topology` | bool | ❌ | `true` | 集群拓扑增强（注入集群拓扑上下文） |

示例：

```json
{
  "question": "MySQL主从复制延迟怎么排查？",
  "db_type": "mysql",
  "use_rag": true,
  "use_topology": true
}
```

> 企业微信接入建议显式传 `use_rag`、`use_topology` 为 `true`（与默认值一致，但更明确）。

### 3.2 响应（HTTP 200）

```json
{
  "answer": "LLM 生成的回答文本……",
  "metadata": {
    "confidence": "high",
    "knowledge_sources": [
      {"title": "……", "content": "……", "score": 0.82}
    ],
    "has_sufficient_knowledge": true,
    "kg_entities": []
  }
}
```

- `answer`：**最终回答文本**，直接回复给用户即可。
- `metadata`：增强检索的引用信息（可选展示，说明"回答参考了哪些知识"）。

### 3.3 错误

| HTTP 状态 | body | 场景 |
|---|---|---|
| 400 | `{"error": "请输入问题"}` | 未传 `question` |
| 500 | `{"error": "<错误信息>"}` | LLM 未配置 / 调用失败 / 其他异常 |

接入方应把 `error` 字段内容回显给用户（或记日志）。

---

## 四、参数详解

### 4.1 `use_rag` — 知识库增强（默认 true）

`true` 时，接口先用向量检索 + 关键词检索，从知识库（`data/knowledge/` 下按数据库类型组织的文档）取出相关文本块注入 prompt，使回答贴近平台知识库内容。知识库为空或检索不到时自动降级，不影响回答。

### 4.2 `use_topology` — 集群拓扑增强（默认 true）

`true` 时，把集群拓扑数据（资源池 / 集群 / 服务器 / 实例等）摘要注入 prompt，回答可参考实际拓扑情况。

### 4.3 `db_type` — 数据库类型

- `"auto"`：接口从问题文本自动识别数据库类型（如提到"MySQL"即识别为 mysql）；识别不到则按不指定类型处理。
- `""`（默认）：不指定数据库类型，按通用方式回答。
- 显式指定（如 `"mysql"`）：强制按该类型检索知识库、拼接 prompt。

可用 `GET /api/db-types` 获取全部类型 id（返回值 `{"types": [{"id":"mysql","name":"MySQL",...}]}`）。

---

## 五、企业微信接入流程

### 5.1 架构

```
企业微信用户发消息
      │
      ▼
企业微信自建应用「接收消息回调」 ──► 你的回调服务（企微后台）
      │                                      │
      │        提取 Content（问题文本）         │  POST /api/qa/ask
      │                                      ▼
      │                              DBSV Admin 问答接口
      │                                      │
      │             返回 answer               │  返回 {answer, metadata}
      ▼                                      ▼
企业微信用户收到回复 ◄── 回调服务把 answer 回复给用户
```

### 5.2 推荐模式：回调被动回复（实时）

1. 在企微管理后台的「应用管理 → 自建应用 → 接收消息」配置回调 URL、Token、EncodingAESKey。
2. 用户在企微给应用发消息时，企微 POST 一个加密 XML 到回调 URL（`MsgType=text`，`Content=问题内容`）。
3. 回调服务：解密 → 取 `Content` → 调 `/api/qa/ask` → 取 `answer` → 按企微加密格式返回被动文本回复。
   - 企微的加解密必须用官方 SDK（见下），**不要手写**。
4. 被动回复有超时要求（约 5 秒内返回），若问答耗时较长，可先返回"正在处理"，再用**主动推送**回结果（见 5.3）。

### 5.3 备选模式：主动推送（异步）

后台先调企微 `gettoken` 获取 `access_token`，再调「发送应用消息」接口把 `answer` 推给指定用户。适合问答耗时超过被动回复时限的场景。

> 企微侧的具体 API / 加解密细节，以企业微信官方文档为准，接入代码可用 `wechatpy` 或企微官方 SDK。

---

## 六、代码示例

### 6.1 Python 调用问答接口（requests）

```python
import requests

BASE_URL = "http://10.126.77.37:9163"   # 改成实际服务地址

def ask_question(question: str, db_type: str = "auto",
                 use_rag: bool = True, use_topology: bool = True,
                 timeout: int = 120) -> dict:
    """
    调用知识问答接口，返回 {'answer': str, 'metadata': dict}
    异常时抛 requests 异常；接口返回错误时在 'error' 键给出错误信息。
    """
    resp = requests.post(
        f"{BASE_URL}/api/qa/ask",
        json={
            "question": question,
            "db_type": db_type,
            "use_rag": use_rag,
            "use_topology": use_topology,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


# 使用示例
result = ask_question("MySQL主从复制延迟怎么排查？", db_type="mysql")
if "error" in result:
    print("出错:", result["error"])
else:
    print("回答:", result["answer"])
```

### 6.2 curl 示例

```bash
curl -X POST http://10.126.77.37:9163/api/qa/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Oracle RAC 如何做备份？","db_type":"oracle","use_rag":true,"use_topology":true}'
```

### 6.3 企业微信回调服务最小骨架（Flask + wechatpy）

```python
from flask import Flask, request, make_response
from wechatpy import parse_message
from wechatpy.replies import TextReply
from wechatpy.utils import check_signature
from wechatpy.crypto import WeChatCrypto   # 企微用 WeChatCrypto / WeComCrypto

import requests

app = Flask(__name__)

WECOM_TOKEN = "your_token"          # 企微回调 Token
WECOM_AES_KEY = "your_encoding_aes_key"   # EncodingAESKey
WECOM_CORP_ID = "your_corpid"
QA_URL = "http://10.126.77.37:9163/api/qa/ask"


@app.route("/wecom/callback", methods=["GET", "POST"])
def wecom_callback():
    # GET：URL 验证
    if request.method == "GET":
        check_signature(WECOM_TOKEN,
                        request.args.get("msg_signature", ""),
                        request.args.get("timestamp", ""),
                        request.args.get("nonce", ""))
        crypto = WeChatCrypto(WECOM_TOKEN, WECOM_AES_KEY, WECOM_CORP_ID)
        echo = crypto.check_signature(
            request.args.get("msg_signature"),
            request.args.get("timestamp"),
            request.args.get("nonce"),
            request.args.get("echostr"),
        )
        return echo

    # POST：接收消息
    crypto = WeChatCrypto(WECOM_TOKEN, WECOM_AES_KEY, WECOM_CORP_ID)
    msg = crypto.decrypt_message(
        request.data,
        request.args.get("msg_signature"),
        request.args.get("timestamp"),
        request.args.get("nonce"),
    )
    parsed = parse_message(msg)

    answer = ""
    if parsed.type == "text":
        question = parsed.content
        try:
            r = requests.post(QA_URL, json={
                "question": question,
                "db_type": "auto",
                "use_rag": True,
                "use_topology": True,
            }, timeout=120)
            data = r.json()
            answer = data.get("answer") or data.get("error", "服务异常")
        except Exception as e:
            answer = f"调用失败: {e}"

    reply = TextReply(content=answer, message=parsed)
    encrypted = crypto.encrypt_message(reply.render())
    resp = make_response(encrypted)
    resp.headers["Content-Type"] = "text/xml"
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

> 企微加解密务必使用 `wechatpy` 或官方 SDK，示例中的类名/方法以你所用 SDK 版本为准。

### 6.4 流式接口（可选，一般不需要）

若确实要流式，用 `POST /api/qa/ask/stream`（SSE）。参数同 3.1，另可加 `model_id`、`conversation_id`（多轮）。事件格式（每行 `data: <json>`，空行分隔）：

```
data: {"type":"metadata","metadata":{...}}
data: {"content":"第1段"}
data: {"content":"第2段"}
data: [DONE]
```

错误时：`data: {"error":"..."}`。企业微信被动回复不支持 SSE，故默认建议用非流式接口。

---

## 七、注意事项

1. **超时**：问答会调用 LLM，耗时可能几十秒。HTTP 客户端 `timeout` 建议 ≥120s；企微被动回复有约 5s 时限，超时场景改走主动推送。
2. **LLM 未配置**：接口返回 500 + error，接入方应提示"系统未配置大模型"。
3. **db_type 自动识别**：传 `"auto"` 才按问题内容识别；`""`（默认）不指定类型，走通用回答。
4. **内网地址**：接口在服务器 9163 端口，企微回调服务需能访问到该地址（内网互通）。
5. **安全**：接口无鉴权，接入层需加 IP 白名单 / 限流 / 网关校验，避免被滥用。
6. **每次独立**：非流式接口是无状态的（不保存会话），符合"每次问答单独一次请求"的约定。

---

## 八、附：获取数据库类型列表

```
GET http://<服务器IP>:9163/api/db-types
```
响应：`{"types": [{"id":"mysql","name":"MySQL","icon":"🐬"}, ...]}`

---

## 相关文件（供开发参考）

- `routes/qa.py`：问答接口实现（`/api/qa/ask`、`/api/qa/ask/stream`）
- `utils/__init__.py`：`call_llm` / `call_llm_stream`（LLM 调用）
- `rag/embedder.py`：向量检索（RAG）
