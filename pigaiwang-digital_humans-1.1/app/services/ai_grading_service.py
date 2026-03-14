"""AI 批改服务。"""

from __future__ import annotations

import base64
import json
import mimetypes
from asyncio import sleep
from pathlib import Path
from typing import Any, Literal

import httpx
from openai import AsyncOpenAI
from openai import APIConnectionError, APITimeoutError
from pydantic import BaseModel, Field

from app.configs import base_configs


FIXED_TYPICAL_ERROR_LIBRARY: tuple[dict[str, str], ...] = (
    {
        "pattern_name": "标准化步骤错误",
        "pattern_desc": "作答过程缺少必要步骤，或书写/化简/表达不规范。",
        "suggestion_text": "按标准步骤完整书写推导过程，并检查表达是否规范。",
    },
    {
        "pattern_name": "对称性误用",
        "pattern_desc": "错误套用了轴对称、中心对称、奇偶性等对称性质。",
        "suggestion_text": "先确认题目是否满足对应对称条件，再使用相关性质。",
    },
    {
        "pattern_name": "不等式转化错误",
        "pattern_desc": "不等式移项、放缩、变形或区间转换时出现错误。",
        "suggestion_text": "逐步检查不等式变形依据，特别注意方向变化和取值范围。",
    },
    {
        "pattern_name": "查表/数值计算错误",
        "pattern_desc": "查表、代值、近似换算或数值计算过程中出现错误。",
        "suggestion_text": "重新核对查表结果、代入数据和每一步计算过程。",
    },
    {
        "pattern_name": "概念混淆",
        "pattern_desc": "对定义、公式、性质或适用条件理解混淆。",
        "suggestion_text": "回到概念定义和公式适用条件，先分清再作答。",
    },
)

FIXED_TYPICAL_ERROR_KEYWORDS: dict[str, tuple[str, ...]] = {
    "标准化步骤错误": (
        "步骤",
        "过程",
        "推导",
        "化简",
        "书写",
        "表达不规范",
        "格式",
        "中间",
    ),
    "对称性误用": (
        "对称",
        "轴对称",
        "中心对称",
        "奇函数",
        "偶函数",
        "奇偶",
    ),
    "不等式转化错误": (
        "不等式",
        "大于",
        "小于",
        "区间",
        "范围",
        "放缩",
        "取值",
        "方向",
    ),
    "查表/数值计算错误": (
        "查表",
        "计算",
        "数值",
        "代入",
        "近似",
        "小数",
        "四舍五入",
        "算错",
    ),
    "概念混淆": (
        "概念",
        "定义",
        "性质",
        "公式",
        "定理",
        "条件",
        "混淆",
        "误解",
    ),
}


class AIGradingTypicalError(BaseModel):
    """AI 识别出的典型错误。"""

    pattern_name: str = Field(min_length=1, max_length=128, description="错误名称")
    pattern_desc: str | None = Field(default=None, description="错误描述")
    suggestion_text: str | None = Field(default=None, description="改进建议")


class AIGradingResult(BaseModel):
    """AI 批改结构化结果。"""

    result_status: Literal["correct", "wrong", "partial", "unanswered"] = Field(
        default="unanswered",
        description="批改结论",
    )
    ai_score: float = Field(default=0, description="AI 评分")
    final_score: float = Field(default=0, description="最终评分")
    ai_feedback: str = Field(default="", description="批改反馈")
    typical_errors: list[AIGradingTypicalError] = Field(
        default_factory=list,
        description="典型错误列表",
    )
    model_name: str = Field(default="", description="模型名称")
    raw_content: str | None = Field(default=None, description="模型原始输出")


class HandwritingNormalizationResult(BaseModel):
    """手写作答识别与归一化结果。"""

    normalized_answer: str = Field(default="", description="归一化后的学生答案")
    ambiguity_notes: str | None = Field(default=None, description="识别歧义说明")
    symbol_mapping_notes: list[str] = Field(
        default_factory=list,
        description="关键符号识别映射说明",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        default="medium",
        description="识别可信度",
    )
    raw_content: str | None = Field(default=None, description="模型原始输出")


class AIGradingService:
    """使用 OpenAI 兼容接口调用千问模型完成作业批改。"""

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        if not base_configs.LLM_API_KEY:
            raise RuntimeError("未配置 LLM_API_KEY，无法调用 AI 批改")
        if self._client is None:
            http_client = httpx.AsyncClient(
                timeout=base_configs.LLM_TIMEOUT_SEC,
                trust_env=base_configs.LLM_TRUST_ENV_PROXY,
            )
            self._client = AsyncOpenAI(
                api_key=base_configs.LLM_API_KEY,
                base_url=base_configs.LLM_BASE_URL,
                timeout=base_configs.LLM_TIMEOUT_SEC,
                max_retries=base_configs.LLM_MAX_RETRIES,
                http_client=http_client,
            )
        return self._client

    def _build_system_prompt(self) -> str:
        return (
            "你是一名严谨且公平的中文老师/阅卷老师，擅长识别学生手写答案、数学符号、公式变形和非标准书写。"
            "请根据题目、参考答案、学生文本答案和学生作答图片进行评分，"
            "只输出 JSON，不要输出任何额外说明。"
            "JSON 字段必须包含：result_status、ai_score、final_score、ai_feedback、typical_errors。"
            "其中 result_status 仅允许 correct、wrong、partial、unanswered。"
            "ai_score 和 final_score 必须是数字，范围在 0 到题目满分之间。"
            "只要学生已作答，就必须给出明确分数，不能省略。"
            "若判定为 correct，则 ai_score 和 final_score 必须等于满分。"
            "typical_errors 固定返回空数组 []，不要自行分析或生成典型错误。"
            "若学生未作答，则 result_status=unanswered，分数为 0。"
            "学生答案可能是手写体、字迹潦草、拍照模糊、存在错别字、简写、非标准数学符号或不规范排版。"
            "评分时必须优先理解学生真实想表达的意思，而不是机械逐字匹配。"
            "如果某些字词、数字、符号难以辨认，请结合上下文、公式结构、解题步骤和常见书写习惯进行合理还原。"
            "对于可以根据上下文明确还原的手写内容，不要因为字不工整、符号不标准而扣分。"
            "只有在关键数字、符号、单位或结论无法可靠辨认，且会影响判分时，才可因识别不确定性酌情扣分。"
            "如果识别存在不确定性但大体思路正确，应尽量给部分分，而不是直接判错。"
            "必须区分手写识别困难与真实知识性错误，不要把字迹潦草直接判定为概念错误或计算错误。"
            "如果学生文本答案与作答图片不一致，以图片中的实际作答内容为主要依据，并在 ai_feedback 中说明。"
            "对于数学手写内容，请特别注意数字、上下标、分数线、根号、括号、正负号、不等号、乘方、除号、相似字符和相近公式的识别容错。"
            "尤其要注意以下常见手写混淆：σ 与 6，μ 与 u，x 与 ×，1 与 l，0 与 O，- 与 _，> 与 ≥，< 与 ≤。"
            "如果某个符号在局部看起来像别的字符，但结合整道题的定义、常用公式、标准记号、前后步骤可以唯一解释，则应按最合理的数学含义理解，不应机械按表面字符判错。"
            "对证明题、推导题、变量替换题、标准化题，应优先评估解题方法、步骤结构和核心思路是否正确。"
            "如果学生整体方法正确，只是个别手写符号存在疑似误识别或孤立记号不工整，应保留大部分方法分，不要因为单个符号外观问题大幅扣分。"
            "只有当符号错误在上下文中可以确定为真实数学错误，并且实质性影响后续推导、结论或数值时，才应按知识性错误扣分。"
            "若某一步既可能是手写识别偏差，也可能是真实错误，且上下文更支持前者，应优先按识别偏差处理。"
            "涉及正态分布、标准化、变量替换时，应特别检查学生是否在尝试使用标准记号 μ、σ、Φ；若手写图片中 6 疑似代替 σ，或其他字符疑似代替标准符号，应先按标准化推导语义理解。"
            "对于方法正确但记号存在局部歧义的答案，反馈中可以提醒书写规范，但分数应主要依据数学思路而非字形。"
        )

    def _build_recognition_system_prompt(self) -> str:
        return (
            "你是一名擅长识别学生手写数学答案的助教。"
            "你的唯一任务是先做手写内容识别与归一化，不要评分。"
            "请结合题目、参考答案、学生文本答案和学生作答图片，输出一个 JSON。"
            "重点识别手写数学符号、变量、公式结构、上下标、分数线、根号、括号和不等号。"
            "尤其注意常见混淆：σ/6、μ/u、x/×、1/l、0/O、-/_、> / ≥、< / ≤。"
            "如果上下文足以唯一确定某个模糊符号的真实数学含义，请按真实含义归一化。"
            "如果不能唯一确定，请在 ambiguity_notes 中说明，不要擅自强行改写。"
            "JSON 字段必须包含：normalized_answer、ambiguity_notes、symbol_mapping_notes、confidence。"
            "不要输出任何额外说明。"
        )

    def _build_user_prompt(
        self,
        *,
        question_content: str | None,
        reference_answer: str | None,
        student_answer: str | None,
        recognition_notes: str | None,
        question_type: str,
        full_score: float,
        known_typical_errors: list[dict[str, Any]],
    ) -> str:
        typical_error_text = "无"
        if known_typical_errors:
            typical_error_text = "\n".join(
                [
                    (
                        f"- 名称：{item.get('pattern_name', '')}；"
                        f"描述：{item.get('pattern_desc') or '无'}；"
                        f"建议：{item.get('suggestion_text') or '无'}"
                    )
                    for item in known_typical_errors
                ]
            )
        return (
            f"题型：{question_type}\n"
            f"满分：{full_score}\n\n"
            f"题目：\n{question_content or '无'}\n\n"
            f"参考答案：\n{reference_answer or '无'}\n\n"
            f"该题已有典型错误模式：\n{typical_error_text}\n\n"
            f"学生答案：\n{student_answer or '无'}\n\n"
            f"手写识别归一化备注：\n{recognition_notes or '无'}\n\n"
            "如果同时提供了作答图片，请结合图片内容一起批改。\n"
            "学生作答可能是手写，字迹不标准、拍照模糊、符号不规范。\n"
            "请结合上下文、公式结构、步骤连续性理解学生真实意图。\n"
            "能合理识别出的内容，按识别后的真实含义评分，不要因字迹问题机械扣分。\n"
            "如果确实无法辨认关键内容，请在 ai_feedback 中明确说明是字迹或符号识别不确定，并按可确认内容保守给分。\n"
            "如果学生思路基本正确但个别手写符号不清，请优先给步骤分或部分分。\n"
            "对于证明题、推导题、变量替换题、标准化题，请优先判断方法是否正确，再判断符号是否只是手写歧义。\n"
            "如果看到类似 σ 写得像 6、μ 写得像 u、乘号像字母 x 等情况，请先结合前后公式与标准记号做语义还原。\n"
            "只在确认这是实质性数学错误时才明显扣分；若更像手写不规范，应保留方法分，并仅在反馈中提醒书写问题。\n"
            "若学生在正态分布分布函数、标准化变换、变量替换等题目中整体结构正确，只是个别符号书写不标准，应优先认定其理解了标准化过程，不要因单个符号外观问题直接低分。\n"
            "当字迹不清与答案错误都可能成立时，优先判断是否存在可被上下文支持的正确解读；若存在，应给出相应部分分，而不是直接判为完全错误。\n\n"
            "请严格返回 JSON，例如："
            '{"result_status":"partial","ai_score":6,"final_score":6,'
            '"ai_feedback":"答案部分正确，步骤不完整",'
            '"typical_errors":[]}'
        )

    def _build_recognition_user_prompt(
        self,
        *,
        question_content: str | None,
        reference_answer: str | None,
        student_answer: str | None,
    ) -> str:
        return (
            f"题目：\n{question_content or '无'}\n\n"
            f"参考答案：\n{reference_answer or '无'}\n\n"
            f"学生文本答案：\n{student_answer or '无'}\n\n"
            "请先做手写作答识别与归一化，而不是评分。\n"
            "若图片里存在疑似手写歧义，请优先结合上下文恢复标准数学记号。\n"
            "例如在正态分布标准化推导中，若某符号局部看似 6，但上下文显示它应为 σ，则应优先归一化为 σ，并在 symbol_mapping_notes 中说明。\n"
            "请输出 JSON，例如："
            '{"normalized_answer":"F(x)=Φ((x-μ)/σ)",'
            '"ambiguity_notes":"手写中疑似将σ写成6，已结合上下文归一化",'
            '"symbol_mapping_notes":["6 -> σ"],'
            '"confidence":"medium"}'
        )

    def _build_fixed_typical_errors(self, ai_feedback: str, result_status: str) -> list[AIGradingTypicalError]:
        if result_status in {"correct", "unanswered"}:
            return []

        feedback_text = (ai_feedback or "").strip()
        selected_names: list[str] = []
        lower_feedback_text = feedback_text.lower()

        for item in FIXED_TYPICAL_ERROR_LIBRARY:
            pattern_name = item["pattern_name"]
            keywords = FIXED_TYPICAL_ERROR_KEYWORDS.get(pattern_name, ())
            if any(keyword.lower() in lower_feedback_text for keyword in keywords):
                selected_names.append(pattern_name)

        if not selected_names:
            if any(keyword in feedback_text for keyword in ("步骤", "过程", "推导", "书写")):
                selected_names.append("标准化步骤错误")
            elif any(keyword in feedback_text for keyword in ("计算", "代入", "结果", "数值")):
                selected_names.append("查表/数值计算错误")
            else:
                selected_names.append("概念混淆")

        fixed_errors: list[AIGradingTypicalError] = []
        selected_name_set = set(selected_names[:3])
        for item in FIXED_TYPICAL_ERROR_LIBRARY:
            if item["pattern_name"] not in selected_name_set:
                continue
            fixed_errors.append(AIGradingTypicalError.model_validate(item))
        return fixed_errors

    def _build_user_content(
        self,
        *,
        question_content: str | None,
        reference_answer: str | None,
        student_answer: str | None,
        recognition_notes: str | None,
        question_type: str,
        full_score: float,
        question_image_urls: list[str],
        image_urls: list[str],
        known_typical_errors: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | str:
        prompt = self._build_user_prompt(
            question_content=question_content,
            reference_answer=reference_answer,
            student_answer=student_answer,
            recognition_notes=recognition_notes,
            question_type=question_type,
            full_score=full_score,
            known_typical_errors=known_typical_errors,
        )
        if not question_image_urls and not image_urls:
            return prompt

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if question_image_urls:
            content.append({"type": "text", "text": "以下是题目配图："})
            for image_url in question_image_urls:
                normalized_image_url = self._normalize_image_url(image_url)
                if not normalized_image_url:
                    continue
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": normalized_image_url},
                    }
                )
        if image_urls:
            content.append({"type": "text", "text": "以下是学生作答图片："})
        for image_url in image_urls:
            normalized_image_url = self._normalize_image_url(image_url)
            if not normalized_image_url:
                continue
            if not image_url:
                continue
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": normalized_image_url},
                }
            )
        return content

    def _build_recognition_user_content(
        self,
        *,
        question_content: str | None,
        reference_answer: str | None,
        student_answer: str | None,
        question_image_urls: list[str],
        image_urls: list[str],
    ) -> list[dict[str, Any]] | str:
        prompt = self._build_recognition_user_prompt(
            question_content=question_content,
            reference_answer=reference_answer,
            student_answer=student_answer,
        )
        if not question_image_urls and not image_urls:
            return prompt

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if question_image_urls:
            content.append({"type": "text", "text": "以下是题目配图："})
            for image_url in question_image_urls:
                normalized_image_url = self._normalize_image_url(image_url)
                if not normalized_image_url:
                    continue
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": normalized_image_url},
                    }
                )
        if image_urls:
            content.append({"type": "text", "text": "以下是学生作答图片："})
            for image_url in image_urls:
                normalized_image_url = self._normalize_image_url(image_url)
                if not normalized_image_url:
                    continue
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": normalized_image_url},
                    }
                )
        return content

    def _normalize_image_url(self, image_url: str) -> str | None:
        """标准化图片输入，支持远程 URL、Data URL 和本地文件路径。"""
        if not image_url:
            return None
        normalized = image_url.strip()
        if not normalized:
            return None
        if normalized.startswith(("http://", "https://", "data:")):
            return normalized

        file_path = Path(normalized)
        if not file_path.is_absolute():
            file_path = Path(base_configs.PROJECT_DIR) / normalized
        if not file_path.exists() or not file_path.is_file():
            return normalized

        mime_type, _ = mimetypes.guess_type(file_path.name)
        mime_type = mime_type or "application/octet-stream"
        encoded = base64.b64encode(file_path.read_bytes()).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"

    def _extract_content_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
                else:
                    text = getattr(item, "text", None)
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return ""

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        text = content.strip()
        if not text:
            raise ValueError("AI 返回内容为空")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def _normalize_status(self, value: str | None) -> str:
        mapping = {
            "correct": "correct",
            "wrong": "wrong",
            "partial": "partial",
            "partial_correct": "partial",
            "unanswered": "unanswered",
            "未作答": "unanswered",
            "正确": "correct",
            "错误": "wrong",
            "部分正确": "partial",
        }
        normalized = mapping.get((value or "").strip().lower(), None)
        if normalized is None:
            normalized = mapping.get((value or "").strip(), "partial")
        return normalized

    def _normalize_score(self, value: Any, full_score: float) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, score)
        return min(score, max(full_score, 0.0))

    def _build_score_fallback(self, result_status: str, full_score: float) -> float:
        normalized_full_score = max(float(full_score or 0), 0.0)
        if result_status == "correct":
            return normalized_full_score
        if result_status == "partial":
            if normalized_full_score <= 0:
                return 0.0
            return min(normalized_full_score, max(round(normalized_full_score * 0.6, 2), 1.0))
        return 0.0

    async def _call_json_model(
        self,
        *,
        model_name: str,
        system_prompt: str,
        user_content: list[dict[str, Any]] | str,
    ) -> tuple[dict[str, Any], str]:
        client = self._get_client()
        last_error: Exception | None = None
        for attempt in range(base_configs.LLM_MAX_RETRIES + 1):
            try:
                response = await client.chat.completions.create(
                    model=model_name,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                )
                break
            except (APIConnectionError, APITimeoutError, httpx.RemoteProtocolError) as exc:
                last_error = exc
                if attempt >= base_configs.LLM_MAX_RETRIES:
                    raise RuntimeError(
                        "AI 服务连接失败，请检查网络、代理或 LLM_BASE_URL 配置"
                    ) from exc
                await sleep(min(2**attempt, 3))
        else:
            raise RuntimeError("AI 服务调用失败") from last_error

        message = response.choices[0].message
        raw_content = self._extract_content_text(message.content)
        return self._parse_json_content(raw_content), raw_content

    async def _normalize_handwritten_answer(
        self,
        *,
        model_name: str,
        question_content: str | None,
        reference_answer: str | None,
        student_answer: str | None,
        question_image_urls: list[str],
        image_urls: list[str],
    ) -> HandwritingNormalizationResult | None:
        if not image_urls:
            return None

        payload, raw_content = await self._call_json_model(
            model_name=model_name,
            system_prompt=self._build_recognition_system_prompt(),
            user_content=self._build_recognition_user_content(
                question_content=question_content,
                reference_answer=reference_answer,
                student_answer=student_answer,
                question_image_urls=question_image_urls,
                image_urls=image_urls,
            ),
        )
        result = HandwritingNormalizationResult.model_validate(payload)
        result.raw_content = raw_content
        return result

    async def grade_answer(
        self,
        *,
        question_content: str | None,
        reference_answer: str | None,
        student_answer: str | None,
        question_type: str,
        full_score: float,
        question_image_urls: list[str],
        image_urls: list[str],
        known_typical_errors: list[dict[str, Any]],
    ) -> AIGradingResult:
        """调用大模型进行批改。"""
        has_answer = bool((student_answer or "").strip() or image_urls)
        model_name = (
            base_configs.LLM_VISION_MODEL_KEY
            if question_image_urls or image_urls
            else base_configs.LLM_MODEL_KEY
        )
        normalization_result = await self._normalize_handwritten_answer(
            model_name=model_name,
            question_content=question_content,
            reference_answer=reference_answer,
            student_answer=student_answer,
            question_image_urls=question_image_urls,
            image_urls=image_urls,
        )

        normalized_student_answer = student_answer or ""
        recognition_notes = "无"
        if normalization_result is not None:
            normalized_parts: list[str] = []
            if student_answer:
                normalized_parts.append(f"原始文本答案：\n{student_answer}")
            if normalization_result.normalized_answer:
                normalized_parts.append(
                    f"根据手写图片归一化后的答案：\n{normalization_result.normalized_answer}"
                )
            normalized_student_answer = "\n\n".join(normalized_parts) or student_answer or ""

            recognition_note_parts = []
            if normalization_result.ambiguity_notes:
                recognition_note_parts.append(normalization_result.ambiguity_notes)
            if normalization_result.symbol_mapping_notes:
                recognition_note_parts.append(
                    "符号归一化：" + "；".join(normalization_result.symbol_mapping_notes)
                )
            recognition_note_parts.append(f"识别可信度：{normalization_result.confidence}")
            recognition_notes = "\n".join(recognition_note_parts)

        payload, raw_content = await self._call_json_model(
            model_name=model_name,
            system_prompt=self._build_system_prompt(),
            user_content=self._build_user_content(
                question_content=question_content,
                reference_answer=reference_answer,
                student_answer=normalized_student_answer,
                recognition_notes=recognition_notes,
                question_type=question_type,
                full_score=full_score,
                question_image_urls=question_image_urls,
                image_urls=image_urls,
                known_typical_errors=known_typical_errors,
            ),
        )
        result = AIGradingResult.model_validate(payload)
        result.result_status = self._normalize_status(result.result_status)
        result.ai_score = self._normalize_score(result.ai_score, full_score)
        result.final_score = self._normalize_score(result.final_score, full_score)
        fallback_score = self._build_score_fallback(result.result_status, full_score)
        if has_answer and result.ai_score <= 0 < fallback_score:
            result.ai_score = fallback_score
        if has_answer and result.final_score <= 0 < fallback_score:
            result.final_score = fallback_score
        if result.ai_score <= 0 < result.final_score:
            result.ai_score = result.final_score
        if result.final_score <= 0 and result.ai_score > 0:
            result.final_score = result.ai_score
        if result.result_status == "correct":
            result.ai_score = max(result.ai_score, float(full_score or 0))
            result.final_score = max(result.final_score, float(full_score or 0))
        if not result.ai_feedback:
            result.ai_feedback = "AI 已完成批改。"
        result.typical_errors = self._build_fixed_typical_errors(
            result.ai_feedback,
            result.result_status,
        )
        result.model_name = model_name
        result.raw_content = raw_content
        return result


ai_grading_service = AIGradingService()
