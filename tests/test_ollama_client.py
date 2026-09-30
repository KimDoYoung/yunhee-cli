import httpx

from yunhee import ollama_client


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _fake_post(captured, data):
    def post(url, json, timeout):
        captured["json"] = json
        return _Resp(data)
    return post


def test_chat_sends_num_ctx(monkeypatch):
    captured = {}
    monkeypatch.setattr(ollama_client, "NUM_CTX", 16384)
    monkeypatch.setattr(httpx, "post", _fake_post(captured, {
        "message": {"content": "ok"}, "prompt_eval_count": 100,
    }))

    assert ollama_client.chat("hi") == "ok"
    assert captured["json"]["options"] == {"num_ctx": 16384}


def test_chat_warns_when_prompt_truncated(monkeypatch, capsys):
    monkeypatch.setattr(ollama_client, "NUM_CTX", 4096)
    monkeypatch.setattr(httpx, "post", _fake_post({}, {
        "message": {"content": "ok"}, "prompt_eval_count": 4096,
    }))

    ollama_client.chat("long prompt")
    assert "num_ctx(4096" in capsys.readouterr().err


def test_chat_no_warning_below_limit(monkeypatch, capsys):
    monkeypatch.setattr(ollama_client, "NUM_CTX", 4096)
    monkeypatch.setattr(httpx, "post", _fake_post({}, {
        "message": {"content": "ok"}, "prompt_eval_count": 4095,
    }))

    ollama_client.chat("short prompt")
    assert capsys.readouterr().err == ""
