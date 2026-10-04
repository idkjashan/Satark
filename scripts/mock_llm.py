"""A stand-in AI model endpoint for testing the LLM roles without a real model.

It speaks the OpenAI Chat Completions API (what Ollama, LM Studio, vLLM and llama.cpp expose), so the
real server talks to it exactly as it would to a local model:

    uv run python scripts/mock_llm.py --port 9100
    SATARK_LLM=local:satark-mock SATARK_LLM_BASE_URL=http://127.0.0.1:9100/v1 \
        uv run uvicorn satark.app:create_app --factory --port 8000

Its replies are scripted (written by the team, acting as the model): it reads the request's output
schema to tell the calls apart (extract, explain, the AI review's plan and assess steps, the chat's plan
and answer steps), answers in the user's language, quotes exact words for the risks it finds, declines
unrelated requests and stock tips, and — on purpose — misbehaves when the text contains a trigger, so
tests can prove the output guards and the verifier:

    [[mock:code]]        first answer contains a code block         [[mock:tip]]   first answer gives a stock tip
    [[mock:ungrounded]]  first answer names INA999999999, and the first assessment quotes words that are not
                         in the message (the verifier sends it back)
    [[mock:500]]         HTTP 500 (fallback path)                   [[mock:slow]]  sleeps 30 s (timeout path)

After a retry prompt ("Fix the errors and try again") it answers cleanly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="satark-mock-llm")

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
PLACEHOLDER = re.compile(r"\[[A-Z]+_\d+\]")
OFF_TOPIC = re.compile(
    r"python|javascript|java\b|c\+\+|\bcode\b|function|program|poem|poetry|story|essay|song|joke|capital of|"
    r"translate|homework|recipe|weather|act as|pretend|role ?play|system prompt|ignore (all|previous)|"
    r"कविता|कहानी|निबंध|चुटकुला|कोड",
    re.I,
)
ADVICE = re.compile(
    r"which (stock|share)|what (stock|share) (should|to)|target price|will .{1,30} (go up|double)|best stock|"
    r"kaun ?sa (share|stock)|konsa share|कौन सा शेयर|कौनसा शेयर|kya kharid",
    re.I,
)
MONEY = re.compile(
    r"invest|stock|share|market|trad|broker|advis|sebi|rbi|nse|bse|demat|mutual fund|sip|nav|ipo|f&o|option|"
    r"leverage|margin|crypto|forex|upi|pay|bank|loan|scam|fraud|profit|return|earn|income|deposit|withdraw|"
    r"wallet|token|coin|airdrop|reward|bonus|prize|lottery|phrase|"
    r"tax|fee|kyc|otp|₹|rs\.?\s?\d|rupee|lakh|crore|paisa|paise|munafa|kamai|निवेश|पैसा|पैसे|रुपये|शेयर|मुनाफा|"
    r"कमा|बैंक|लोन|धोखा|ठगी|सेबी|ट्रेडिंग",
    re.I,
)
QUESTION = re.compile(r"\?\s*$|^(what|how|why|when|is|are|can|should|kya|kaise|kyun|क्या|कैसे|क्यों)\b", re.I)
AWARENESS = re.compile(r"beware|awareness|never share|be careful|stay alert|warns?\b|सावधान|जागरूक", re.I)
NOTICE = re.compile(r"debited|credited|contract note|trade confirmation|matures|statement for|auto-renew|"
                    r"no action required|डेबिट|क्रेडिट", re.I)
# (pattern, code, English title, Hindi title): what the scripted "model" spots, always quoting the message
RISKS = [
    (r"(recovery|seed|secret) (phrase|words)", "AI_RISK_PATTERN", "Asks for your wallet recovery phrase.",
     "आपके वॉलेट का रिकवरी फ़्रेज़ माँगता है।"),
    (r"guarantee\w*[^.।]{0,30}", "GUARANTEED_RETURN", "Promises a guaranteed return.", "पक्के मुनाफ़े का वादा करता है।"),
    (r"withdraw[^.।]{0,40}(fee|charge|tax)|(fee|charge|tax)[^.।]{0,40}withdraw", "FEE_TO_WITHDRAW",
     "Wants a fee before you can withdraw.", "पैसे निकालने से पहले फ़ीस माँगता है।"),
    (r"\b(otp|pin)\b", "OTP_REQUEST", "Asks for your OTP or PIN.", "आपका OTP या PIN माँगता है।"),
    (r"anydesk|teamviewer|screen ?share", "REMOTE_ACCESS_REQUEST", "Wants remote access to your phone.",
     "आपके फ़ोन का रिमोट कंट्रोल माँगता है।"),
    (r"vip (group|channel)|telegram group", "VIP_GROUP", "Pulls you into a private tips group.", "एक प्राइवेट टिप्स ग्रुप में बुलाता है।"),
    (r"today only|final call|last chance|within \d+ ?(hrs|hours)", "URGENCY", "Pushes you to act fast.", "जल्दी करने का दबाव डालता है।"),
]

LESSONS = {
    "sip": ("lesson_compounding", "A SIP (systematic investment plan) puts a fixed amount into a mutual fund every month, "
            "like a monthly recurring deposit, but the value goes up and down with the market.",
            "SIP का मतलब है हर महीने एक तय रकम म्यूचुअल फंड में डालना, जैसे आवर्ती जमा, पर इसकी कीमत बाज़ार के साथ ऊपर-नीचे होती है।"),
    "nav": ("learn", "NAV is the value of one mutual fund unit. A low NAV does not mean a fund is cheap; "
            "what matters is the percentage change.",
            "NAV म्यूचुअल फंड की एक यूनिट की कीमत है। कम NAV का मतलब सस्ता फंड नहीं है; प्रतिशत बदलाव मायने रखता है।"),
    "compound": ("lesson_compounding", "Compounding means returns earn more returns, so growth speeds up. "
                 "That is also why '1% a day' is impossible to promise: it would be about 12 times your money in a year.",
                 "चक्रवृद्धि में मुनाफे पर भी मुनाफा मिलता है। इसीलिए 'रोज़ 1%' का वादा झूठा है: यह साल में लगभग 12 गुना होगा।"),
    "leverage": ("sim_s3", "Leverage means trading a bigger amount than your money by borrowing. At 8 times leverage, "
                 "a 12% fall can wipe out your whole margin.",
                 "लीवरेज में उधार लेकर अपनी रकम से बड़ा सौदा किया जाता है। 8 गुना लीवरेज पर 12% गिरावट पूरी रकम डुबो सकती है।"),
    "mutual fund": ("learn", "A mutual fund pools many people's money and a registered fund house invests it. "
                    "Check the fund on AMFI's website and never pay into a personal account.",
                    "म्यूचुअल फंड कई लोगों का पैसा मिलाकर निवेश करता है। फंड हाउस SEBI में रजिस्टर्ड होता है; निजी खाते में कभी पैसा न भेजें।"),
}


# ---- helpers -----------------------------------------------------------------------------------
def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # multimodal parts
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _has_image(messages: list[dict]) -> bool:
    for m in messages:
        c = m.get("content")
        if isinstance(c, list) and any(isinstance(p, dict) and p.get("type") == "image_url" for p in c):
            return True
    return False


def _json_objects(text: str) -> list[Any]:
    """Every top-level JSON object embedded in a text (briefs, schemas)."""
    out, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(text):
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    out.append(json.loads(text[start : i + 1]))
                except ValueError:
                    pass
    return out


def _brief(user_text: str) -> dict:
    for obj in _json_objects(user_text):
        if isinstance(obj, dict) and ({"masked_text", "verdict", "entities"} & set(obj)):
            return obj
    return {}


def _untrusted(user_text: str, brief: dict) -> str:
    src = brief.get("masked_text") or user_text
    m = re.search(r"<untrusted_message>(.*?)</untrusted_message>", src, re.S)
    return (m.group(1) if m else src).strip()


def _role(schema: dict, prompt: str) -> str:
    props = set((schema or {}).get("properties", {}))
    if {"reasoning", "risk_factors"} <= props:
        return "assess"
    if "done" in props:  # an agent-loop step (agent.py): pick lookups from the menu, or stop
        return "step"
    if {"screen", "visible_text"} <= props:
        return "image"
    if {"summary", "reasons"} <= props:
        return "explain"
    if "text" in props and ("cites" in props or "refused" in props):
        return "respond"
    if "claims" in props or "is_question" in props:
        return "extract"
    low = prompt.lower()
    return "explain" if '"summary"' in low else "respond" if '"cites"' in low else "extract"


def _default_for(s: dict, defs: dict) -> Any:
    if "$ref" in s:
        s = defs.get(s["$ref"].split("/")[-1], {})
    if "default" in s:
        return s["default"]
    if "enum" in s:
        return s["enum"][0]
    for alt in s.get("anyOf", []):
        if alt.get("type") == "null":
            return None
    t = s.get("type")
    return {"string": "", "boolean": False, "integer": 0, "number": 0, "array": [], "object": {}}.get(t)


def _conform(obj: Any, schema: dict, defs: dict) -> Any:
    """Drop unknown keys, fill required ones, and drop list items whose enum value is not allowed."""
    if "$ref" in schema:
        schema = defs.get(schema["$ref"].split("/")[-1], {})
    if "anyOf" in schema and obj is not None:
        non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
        return _conform(obj, non_null[0], defs) if non_null else obj
    if schema.get("type") == "object" and isinstance(obj, dict) and "properties" in schema:
        props = schema["properties"]
        out = {k: _conform(v, props[k], defs) for k, v in obj.items() if k in props}
        for k in schema.get("required", []):
            out.setdefault(k, _default_for(props.get(k, {}), defs))
        return out
    if schema.get("type") == "array" and isinstance(obj, list):
        item = schema.get("items", {})
        if "$ref" in item:
            item = defs.get(item["$ref"].split("/")[-1], {})
        enum = (item.get("properties", {}).get("type", {}) or {}).get("enum")
        items = [x for x in obj if not (enum and isinstance(x, dict) and x.get("type") not in enum)]
        return [_conform(x, item, defs) for x in items]
    if "enum" in schema and obj not in schema["enum"]:
        return schema["enum"][0]
    return obj


# ---- the three roles ("the model") --------------------------------------------------------------
def _extract(text: str, image: bool) -> dict:
    if image:
        text = "VIP Trading Group: your withdrawal is blocked. Pay 18% tax ₹12,600 to unlock. UPI: profit.desk@ybl"
    low = text.lower()
    claims: list[dict] = []

    def claim(t: str, **attrs: Any) -> None:
        claims.append({"type": t, "attrs": attrs, "refs": [], "quote": text[:100]})

    if re.search(r"guarante|assured|pakka|sure.?shot|गारंटी|पक्का", low):
        claim("claim.guaranteed_return")
    if re.search(r"vip|join .{0,20}group|telegram group|ग्रुप", low):
        claim("request.join_group", platform="whatsapp")
    if re.search(r"withdraw|nikal|निकास|निकाल", low) and re.search(r"tax|fee|charge|unlock|टैक्स|शुल्क", low):
        claim("request.fee_to_withdraw")
    if re.search(r"anydesk|teamviewer|quick ?support|rustdesk|screen ?share", low):
        claim("request.remote_access")
    if re.search(r"\botp\b|\bpin\b|password|ओटीपी", low) and re.search(r"share|send|bata|batao|भेज|बताएं", low):
        claim("request.credentials", kind="otp")
    if re.search(r"institutional|\bfpi\b|\bqib\b|ipo allotment|pre-?ipo", low):
        claim("claim.institutional_access")
    if re.search(r"arrest|\bcbi\b|police|account freeze|गिरफ्तार", low):
        claim("threat.legal_action", kind="digital_arrest")
    if re.search(r"urgent|today only|limited|sirf aaj|jaldi|अभी|सीमित", low):
        claim("pressure.urgency")
    if re.search(r"sebi (registered|regd)|registered with sebi|सेबी रजिस्टर्ड|सेबी पंजीकृत", low):
        refs = PLACEHOLDER.findall(text)
        claims.append({"type": "claim.registered_as", "attrs": {"regulator": "SEBI"}, "refs": refs, "quote": text[:100]})
    if re.search(r"(from|on behalf of) sebi|sebi notice|sebi official|सेबी की ओर से", low):
        claim("claim.impersonates", org="SEBI", kind="regulator", brand_id="sebi")
    words = len(text.split())
    return {
        "language": "hi" if DEVANAGARI.search(text) else "en",
        "is_question": bool(QUESTION.search(text.strip())) and words <= 30 and not PLACEHOLDER.search(text),
        "related_to_money": bool(MONEY.search(text) or PLACEHOLDER.search(text)) and not (OFF_TOPIC.search(text) and not MONEY.search(text)),
        "ocr_text": text if image else None,
        "ocr_confidence": "ok",
        "entities": [],
        "claims": claims,
    }


HEADLINES = {
    "HIGH_RISK": ("This looks like a scam. Do not pay", "यह धोखा लगता है। पैसे न भेजें"),
    "SUSPICIOUS": ("This looks suspicious. Check before you act", "यह संदिग्ध है। कुछ भी करने से पहले जाँचें"),
    "NO_SIGNS": ("We found no strong risk signs, but please still verify", "कोई बड़ा खतरा नहीं दिखा, फिर भी जाँच ज़रूर करें"),
    "UNKNOWN": ("We could not check this fully", "हम इसे पूरी तरह जाँच नहीं पाए"),
}


def _explain(brief: dict, misbehave: str | None) -> dict:
    lang = brief.get("lang", "en")
    hi = lang == "hi"
    v = brief.get("verdict") or {}
    level = v.get("level", "UNKNOWN")
    reasons = v.get("reasons", [])
    head = HEADLINES.get(level, HEADLINES["UNKNOWN"])[1 if hi else 0]
    titles = "; ".join(r.get("title", r.get("code", "")) for r in reasons[:3])
    tail = "पैसे भेजने से पहले आधिकारिक वेबसाइट पर जाँच करें।" if hi else "Check on the official website before you pay or share anything."
    summary = f"{head}. {titles}. {tail}" if titles else f"{head}. {tail}"
    if misbehave == "ungrounded":
        summary += " The adviser INA999999999 is registered."
    if misbehave == "tip":
        summary += " Buy RELIANCE at ₹2500, target ₹2800."
    if misbehave == "code":
        summary += "\n```python\nprint('hi')\n```"
    chips = ["अब मैं क्या करूँ?", "सलाहकार की जाँच कैसे करें?"] if hi else ["What should I do now?", "How do I check an adviser?"]
    return {"summary": summary, "reasons": [{"code": r.get("code"), "text": r.get("title") or r.get("code")} for r in reasons[:3]],
            "chips": chips}


def _kind(text: str) -> str:
    if OFF_TOPIC.search(text) and not MONEY.search(text):
        return "unrelated"
    if AWARENESS.search(text):
        return "awareness_or_lesson"
    if NOTICE.search(text):
        return "routine_notice"
    if QUESTION.search(text.strip()) and not any(re.search(p, text, re.I) for p, *_ in RISKS):
        return "question"
    return "message_to_check" if MONEY.search(text) else "unrelated"


def _step(prompt: str, text: str, schema: dict) -> dict:
    """One agent-loop step: on the first step pick every suggested lookup (at most 3) and stop; later steps stop."""
    props = (schema or {}).get("properties", {})
    menu = re.findall(r"^(A\d+) ", prompt.split("Possible lookups:", 1)[-1], re.M) if "Possible lookups:" in prompt else []
    first = "Step 1 of" in prompt
    out = {"thought": "Look up what the message names, then decide.", "pick": menu[:3] if first else [],
           "web_search": "", "add": [], "done": True}
    if "message_kind" in props:
        out["message_kind"] = _kind(text)
        out["sender"] = "the sender of the message"
        out["asks_reader_to"] = "pay, share or join something" if out["message_kind"] == "message_to_check" else "nothing"
    return out


def _assess(text: str, brief: dict, misbehave: str | None) -> dict:
    hi = brief.get("lang") == "hi"
    kind = _kind(text)
    factors = []
    if kind == "message_to_check":
        for pattern, code, en, hi_title in RISKS:
            if m := re.search(pattern, text, re.I):
                factors.append({"code": code, "title": hi_title if hi else en, "quote": m.group(0), "evidence_ids": []})
    if misbehave == "ungrounded":
        factors = [{"code": "GUARANTEED_RETURN", "title": "Promises a guaranteed return.",
                    "quote": "words that are not in the message", "evidence_ids": []}]
    if factors:
        summary = ("इस मैसेज में धोखे के निशान हैं: " + " ".join(f["title"] for f in factors[:3]) + " पैसे न भेजें, पहले जाँच करें।"
                   if hi else "This message shows scam signs: " + " ".join(f["title"] for f in factors[:3])
                   + " Do not pay or share anything until you verify it.")
    elif kind == "awareness_or_lesson":
        summary = ("यह धोखे से बचने की चेतावनी है, खुद कोई ऑफ़र नहीं।" if hi
                   else "This is a warning about scams, not an offer itself. Its advice is sound.")
    else:
        summary = ("हमें इस मैसेज में कोई बड़ा खतरा नहीं दिखा, फिर भी आधिकारिक ऐप या वेबसाइट से पुष्टि करें।" if hi
                   else "We did not see strong scam signs, but confirm through the official app or website.")
    if misbehave == "tip":
        summary += " Buy RELIANCE at ₹2500, target ₹2800."
    chips = ["अब मैं क्या करूँ?", "इसकी शिकायत कहाँ करूँ?"] if hi else ["What should I do now?", "Where do I report this?"]
    asks = "pay, share or join something" if kind == "message_to_check" else "nothing"
    return {"sender": "the sender of the message", "asks_reader_to": asks,
            "reasoning": f"The message is a {kind}; {len(factors)} risk(s) quoted.", "message_kind": kind,
            "scam_type": None, "risk_factors": factors, "summary": summary, "chips": chips}


def _respond(question: str, brief: dict, tool_results: list[str], tools: set[str], misbehave: str | None) -> dict:
    hi = bool(DEVANAGARI.search(question)) or brief.get("lang") == "hi"
    if misbehave == "code":
        return {"text": "Here you go:\n```python\ndef reverse(s): return s[::-1]\n```", "cites": [], "actions": [], "chips": []}
    if misbehave == "tip":
        return {"text": "Buy TATASTEEL now at ₹150, target ₹180, stop loss ₹140.", "cites": [], "actions": [], "chips": []}
    if misbehave == "ungrounded":
        return {"text": "This adviser INA999999999 is registered with SEBI.", "cites": [], "actions": [], "chips": []}
    if OFF_TOPIC.search(question) and not tool_results:
        text = ("मैं सिर्फ पैसों की सुरक्षा में मदद करता हूँ: संदिग्ध मैसेज, लिंक या UPI ID जाँचना, धोखे के बाद क्या करें, और निवेश को आसान भाषा में समझना।"
                if hi else "I can only help with money safety: checking a suspicious message, link or UPI ID, what to do after "
                "a fraud, and learning how investing works.")
        chips = ["SIP क्या है?", "नकली सलाहकार कैसे पहचानें?"] if hi else ["What is a SIP?", "How do I spot a fake adviser?"]
        return {"text": text, "cites": [], "actions": ["learn"], "chips": chips, "refused": "off_topic"}
    if ADVICE.search(question) and not tool_results:
        text = ("मैं किसी शेयर की सलाह या टारगेट नहीं देता। किसी भी सलाह से पहले देखें कि सलाहकार SEBI में रजिस्टर्ड है या नहीं।"
                if hi else "I never suggest stocks or targets. Before following any advice, check that the adviser is "
                "registered with SEBI and never trust guaranteed returns.")
        return {"text": text, "cites": [], "actions": ["lesson_tips_and_pumps"], "chips": [], "refused": "advice"}
    if tool_results:
        joined = " ".join(tool_results)
        codes = sorted(set(re.findall(r"\b[A-Z]{3,}(?:_[A-Z0-9]+)+\b", joined)))
        risky = [c for c in codes if c not in {"REG_FOUND", "DOMAIN_OFFICIAL", "DOMAIN_OLD", "UPI_VALID_HANDLE"}]
        if risky:
            text = (f"जाँच में ये खतरे मिले: {', '.join(risky[:3])}। पैसे न भेजें।" if hi
                    else f"The checks found warning signs ({', '.join(risky[:3])}). Do not pay.")
            actions = ["dont_pay", "report_1930"]
        else:
            text = ("जाँच में कोई बड़ा खतरा नहीं मिला, फिर भी आधिकारिक साइट पर पुष्टि करें।" if hi
                    else "The checks found no strong risk signs, but still confirm on the official website.")
            actions = ["verify_sebi_register"]
        ev = re.findall(r"\bev\d+\b", joined)[:3]
        return {"text": text, "cites": ev, "actions": actions, "chips": []}
    low = question.lower()
    for key, (action, en, hi_text) in LESSONS.items():
        if key in low or (key == "sip" and "एसआईपी" in question):
            return {"text": hi_text if hi else en, "cites": [], "actions": [action], "chips": []}
    text = ("किसी भी निवेश ऑफर पर भरोसा करने से पहले SEBI रजिस्ट्रेशन जाँचें, @valid UPI ID देखें, और गारंटीड रिटर्न के वादों से बचें।"
            if hi else "Before trusting any investment offer, check the SEBI registration, look for an @valid UPI ID, "
            "and treat guaranteed returns as a red flag.")
    return {"text": text, "cites": [], "actions": ["verify_sebi_register"], "chips": []}


# ---- the endpoint -------------------------------------------------------------------------------
def _completion(model: str, content: str | None = None, tool_calls: list[dict] | None = None) -> dict:
    msg: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {
        "id": f"chatcmpl-mock-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if tool_calls else "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


@app.get("/v1/models")
async def models() -> dict:
    return {"object": "list", "data": [{"id": "satark-mock", "object": "model", "owned_by": "satark"}]}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    req = await request.json()
    messages: list[dict] = req.get("messages", [])
    tools = {t["function"]["name"]: t["function"] for t in req.get("tools", []) if t.get("type") == "function"}
    system = "\n".join(_text_of(m.get("content")) for m in messages if m.get("role") in ("system", "developer"))
    users = [_text_of(m.get("content")) for m in messages if m.get("role") == "user"]
    user_text = "\n".join(users)
    retry_msgs = [m for m in messages if "Fix the errors and try again" in (_text_of(m.get("content")) or "")]
    retried = bool(retry_msgs)
    tool_results = [_text_of(m.get("content")) for m in messages if m.get("role") == "tool" and m not in retry_msgs]

    schema, mode = {}, "prompted"
    if "final_result" in tools:
        schema, mode = tools["final_result"].get("parameters", {}), "tool"
    elif (rf := req.get("response_format")) and rf.get("type") == "json_schema":
        schema, mode = rf["json_schema"].get("schema", {}), "native"
    else:
        for obj in _json_objects(system):
            if isinstance(obj, dict) and "properties" in obj:
                schema = obj
                break
    defs = schema.get("$defs", {})
    role = _role(schema, system + user_text)
    brief = _brief(user_text)
    untrusted = _untrusted(user_text, brief)
    trigger = re.search(r"\[\[mock:([a-z0-9-]+)\]\]", user_text)
    misbehave = None if retried or not trigger else trigger.group(1)
    if misbehave == "500":
        return JSONResponse({"error": {"message": "mock failure"}}, status_code=500)
    if misbehave == "slow":
        await asyncio.sleep(30)

    if role == "extract":
        out = _extract(untrusted, _has_image(messages))
    elif role == "explain":
        out = _explain(brief, misbehave)
    elif role == "step":
        out = _step(user_text, untrusted, schema)
    elif role == "image":
        out = {"screen": "chat screenshot", "visible_text": "", "description": "A chat message shown in the screenshot.",
               "cues": []}
    elif role == "assess":
        out = _assess(untrusted, brief, misbehave)
    elif "The user now says:" in user_text:  # the chat's answer step (respond.py): the last block is the user's turn
        question = re.findall(r"<untrusted_message>(.*?)</untrusted_message>", user_text, re.S)[-1].strip()
        found = [json.dumps(brief.get("evidence", []))] if any(e.get("status") == "hit" for e in brief.get("evidence", [])) else []
        if "\nLookups:\n" in user_text:
            found.append(user_text.split("\nLookups:\n", 1)[1])
        risky_q = bool(PLACEHOLDER.search(question)) or "risky" in question.lower() or "check" in question.lower()
        out = _respond(question, brief, found if risky_q else [], set(tools), misbehave)
        out["request"] = {"off_topic": "not_about_money", "advice": "stock_tip_request"}.get(
            out.get("refused") or "", "money_or_scam_question")
    else:
        question = users[-1] if users else ""
        q_brief = _brief(question)
        if q_brief:  # the question may be embedded in a JSON brief
            question = q_brief.get("question") or q_brief.get("message") or _untrusted(question, q_brief)
        entity_ids = [e.get("id") for e in (brief.get("entities") or []) if e.get("type") != "message.text"]
        wants_check = bool(PLACEHOLDER.search(question)) or ("check" in question.lower() and entity_ids)
        if "check_entities" in tools and wants_check and not tool_results and not misbehave:
            ids = [e.get("id") for e in (brief.get("entities") or []) if e.get("id")] or ["e1"]
            call = {"id": f"call_{int(time.time() * 1000)}", "type": "function",
                    "function": {"name": "check_entities", "arguments": json.dumps({"entity_ids": ids})}}
            return _completion(req.get("model", "satark-mock"), tool_calls=[call])
        out = _respond(question, brief, tool_results, set(tools), misbehave)

    out = _conform(out, schema, defs) if schema else out
    if mode == "tool":
        call = {"id": f"call_{int(time.time() * 1000)}", "type": "function",
                "function": {"name": "final_result", "arguments": json.dumps(out, ensure_ascii=False)}}
        return _completion(req.get("model", "satark-mock"), tool_calls=[call])
    return _completion(req.get("model", "satark-mock"), content=json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9100)
    uvicorn.run(app, host="127.0.0.1", port=ap.parse_args().port, log_level="warning")
