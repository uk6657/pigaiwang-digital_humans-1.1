"""答案 AI 批改服务。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from loguru import logger
from sqlalchemy import case, delete, func, select

from app.configs import base_configs
from app.core import s3_client
from app.storage import AsyncSessionLocal, GradingStatus, ResultStatus, SubmissionStatus
from app.storage.database_models import (
    AIGradingLog,
    AnswerTypicalErrorRel,
    ClassStudent,
    ClassStudentStatus,
    Question,
    QuestionImage,
    Quiz,
    QuizClassRel,
    QuizQuestion,
    QuizSubmission,
    SubmissionAnswer,
    SubmissionAnswerImage,
    TypicalErrorPattern,
)

from .ai_grading_service import AIGradingResult, ai_grading_service


@dataclass(slots=True)
class AnswerGradingContext:
    """单个答案批改上下文。"""

    answer_id: int
    submission_id: int
    quiz_id: int
    question_id: int
    student_id: int
    question_content: str | None
    reference_answer: str | None
    question_type: str
    question_image_urls: list[str]
    student_answer: str | None
    image_urls: list[str]
    known_typical_errors: list[dict[str, str | None]]
    full_score: float


class AnswerGradingService:
    """负责调度与落库 AI 批改结果。"""

    @staticmethod
    def _get_image_bucket_name() -> str:
        candidate_attr_names = [
            "QUESTION_IMAGE_BUCKET",
            "QUESTION_S3_BUCKET",
            "S3_BUCKET_NAME",
            "S3_BUCKET",
            "RUSTFS_BUCKET",
        ]
        for attr_name in candidate_attr_names:
            bucket_name = getattr(base_configs, attr_name, None)
            if bucket_name:
                return str(bucket_name)
        raise ValueError("未找到图片桶配置，请补充 QUESTION_IMAGE_BUCKET / S3_BUCKET_NAME")

    def schedule_grade_answer(self, answer_id: int) -> None:
        """异步调度批改任务。"""
        task = asyncio.create_task(self.grade_answer(answer_id))
        task.add_done_callback(self._handle_background_result)

    def schedule_grade_submission(self, submission_id: int) -> None:
        """异步调度整份测验的批改任务。"""
        task = asyncio.create_task(self.grade_submission(submission_id))
        task.add_done_callback(self._handle_background_result)

    def _handle_background_result(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except Exception:
            logger.exception("后台 AI 批改任务执行失败")

    async def _load_submission_answer_ids(self, submission_id: int) -> list[int]:
        async with AsyncSessionLocal() as session:
            rows = await session.execute(
                select(SubmissionAnswer.id)
                .where(
                    SubmissionAnswer.submission_id == submission_id,
                    SubmissionAnswer.is_answered.is_(True),
                    SubmissionAnswer.grading_status != GradingStatus.graded,
                )
                .order_by(SubmissionAnswer.sort_no.asc(), SubmissionAnswer.id.asc())
            )
            return list(rows.scalars().all())

    async def _load_context(self, answer_id: int) -> AnswerGradingContext | None:
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    select(
                        SubmissionAnswer,
                        QuizSubmission,
                        Question,
                        QuizQuestion,
                        Quiz,
                    )
                    .join(
                        QuizSubmission,
                        QuizSubmission.id == SubmissionAnswer.submission_id,
                    )
                    .join(Question, Question.id == SubmissionAnswer.question_id)
                    .join(Quiz, Quiz.id == SubmissionAnswer.quiz_id)
                    .join(
                        QuizQuestion,
                        (QuizQuestion.quiz_id == SubmissionAnswer.quiz_id)
                        & (QuizQuestion.question_id == SubmissionAnswer.question_id),
                    )
                    .where(SubmissionAnswer.id == answer_id)
                )
            ).first()
            if row is None:
                return None
            answer, submission, question, quiz_question, quiz = row
            full_score = float(quiz_question.score or 0)
            if full_score <= 0:
                question_count = int(submission.question_count or 0)
                quiz_total_score = float(getattr(quiz, "total_score", 0) or 0)
                if question_count > 0 and quiz_total_score > 0:
                    full_score = round(quiz_total_score / question_count, 2)
                else:
                    full_score = 100.0
            question_image_urls = (
                (
                    await session.execute(
                        select(QuestionImage.image_url)
                        .where(QuestionImage.question_id == question.id)
                        .order_by(QuestionImage.sort_no.asc(), QuestionImage.id.asc())
                    )
                )
                .scalars()
                .all()
            )
            image_urls = (
                (
                    await session.execute(
                        select(SubmissionAnswerImage.image_url)
                        .where(SubmissionAnswerImage.answer_id == answer.id)
                        .order_by(
                            SubmissionAnswerImage.sort_no.asc(),
                            SubmissionAnswerImage.id.asc(),
                        )
                    )
                )
                .scalars()
                .all()
            )
            bucket_name = self._get_image_bucket_name()
            resolved_question_image_urls: list[str] = []
            for image_url in question_image_urls:
                resolved_question_image_urls.append(
                    await s3_client.resolve_download_url(image_url, bucket_name)
                )
            resolved_answer_image_urls: list[str] = []
            for image_url in image_urls:
                resolved_answer_image_urls.append(
                    await s3_client.resolve_download_url(image_url, bucket_name)
                )
            typical_error_rows = (
                await session.execute(
                    select(TypicalErrorPattern)
                    .where(TypicalErrorPattern.question_id == question.id)
                    .order_by(TypicalErrorPattern.hit_count.desc(), TypicalErrorPattern.id.asc())
                )
            ).scalars().all()
            return AnswerGradingContext(
                answer_id=answer.id,
                submission_id=submission.id,
                quiz_id=answer.quiz_id,
                question_id=answer.question_id,
                student_id=submission.student_id,
                question_content=question.content_md,
                reference_answer=question.reference_answer,
                question_type=question.question_type.value,
                question_image_urls=resolved_question_image_urls,
                student_answer=answer.answer_md,
                image_urls=resolved_answer_image_urls,
                known_typical_errors=[
                    {
                        "pattern_name": item.pattern_name,
                        "pattern_desc": item.pattern_desc,
                        "suggestion_text": item.suggestion_text,
                    }
                    for item in typical_error_rows
                ],
                full_score=full_score,
            )

    async def _mark_answer_grading(self, answer_id: int) -> None:
        async with AsyncSessionLocal() as session:
            answer = await session.get(SubmissionAnswer, answer_id)
            if answer is None or not answer.is_answered:
                return
            answer.grading_status = GradingStatus.grading
            submission = await session.get(QuizSubmission, answer.submission_id)
            if (
                submission is not None
                and submission.answered_count >= submission.question_count
            ):
                submission.status = SubmissionStatus.grading
            await session.commit()

    async def _upsert_typical_errors(
        self,
        *,
        answer_id: int,
        question_id: int,
        typical_errors: list,
    ) -> None:
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(AnswerTypicalErrorRel).where(
                    AnswerTypicalErrorRel.answer_id == answer_id
                )
            )
            for index, item in enumerate(typical_errors):
                pattern = (
                    await session.execute(
                        select(TypicalErrorPattern).where(
                            TypicalErrorPattern.question_id == question_id,
                            TypicalErrorPattern.pattern_name == item.pattern_name,
                        )
                    )
                ).scalar_one_or_none()
                if pattern is None:
                    pattern = TypicalErrorPattern(
                        question_id=question_id,
                        pattern_name=item.pattern_name,
                        pattern_desc=item.pattern_desc,
                        suggestion_text=item.suggestion_text,
                        hit_count=1,
                    )
                    session.add(pattern)
                    await session.flush()
                else:
                    pattern.pattern_desc = item.pattern_desc or pattern.pattern_desc
                    pattern.suggestion_text = (
                        item.suggestion_text or pattern.suggestion_text
                    )
                    pattern.hit_count += 1

                session.add(
                    AnswerTypicalErrorRel(
                        answer_id=answer_id,
                        pattern_id=pattern.id,
                        is_primary=index == 0,
                    )
                )
            await session.commit()

    async def _refresh_submission_summary(self, submission_id: int) -> None:
        async with AsyncSessionLocal() as session:
            submission = await session.get(QuizSubmission, submission_id)
            if submission is None:
                return

            quiz_question_total_score = (
                await session.execute(
                    select(func.coalesce(func.sum(QuizQuestion.score), 0.0)).where(
                        QuizQuestion.quiz_id == submission.quiz_id
                    )
                )
            ).scalar_one()

            total_row = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(SubmissionAnswer.final_score), 0.0),
                        func.coalesce(func.sum(SubmissionAnswer.duration_sec), 0),
                        func.count(
                            case(
                                (
                                    SubmissionAnswer.result_status
                                    == ResultStatus.correct,
                                    1,
                                )
                            )
                        ),
                        func.count(case((SubmissionAnswer.is_answered.is_(True), 1))),
                        func.count(
                            case(
                                (
                                    SubmissionAnswer.grading_status
                                    == GradingStatus.graded,
                                    1,
                                )
                            )
                        ),
                    ).where(SubmissionAnswer.submission_id == submission_id)
                )
            ).one()

            final_score, total_duration, correct_count, answered_count, graded_count = (
                total_row
            )
            question_count = submission.question_count or 0
            calculated_final_score = float(final_score or 0)
            max_total_score = float(quiz_question_total_score or 0)
            if (
                submission.submitted_at is not None
                and calculated_final_score < 10
            ):
                calculated_final_score = min(10.0, max_total_score) if max_total_score > 0 else 10.0
            submission.final_score = calculated_final_score
            submission.total_duration_sec = int(total_duration or 0)
            submission.correct_count = int(correct_count or 0)
            submission.answered_count = int(answered_count or 0)
            submission.accuracy_rate = (
                round((submission.correct_count / question_count) * 100, 2)
                if question_count > 0
                else 0
            )

            if submission.submitted_at is None and submission.answered_count < question_count:
                submission.status = SubmissionStatus.in_progress
            elif graded_count >= submission.answered_count:
                submission.status = SubmissionStatus.reviewed
            else:
                submission.status = SubmissionStatus.grading

            quiz_class_rel = (
                await session.execute(
                    select(QuizClassRel).where(
                        QuizClassRel.quiz_id == submission.quiz_id,
                        QuizClassRel.class_id == submission.class_id,
                    )
                )
            ).scalar_one_or_none()
            if quiz_class_rel is not None:
                target_student_count = int(
                    (
                        await session.execute(
                            select(func.count(ClassStudent.id)).where(
                                ClassStudent.class_id == submission.class_id,
                                ClassStudent.join_status == ClassStudentStatus.active,
                            )
                        )
                    ).scalar_one()
                    or 0
                )
                submitted_student_count = int(
                    (
                        await session.execute(
                            select(func.count(func.distinct(QuizSubmission.student_id))).where(
                                QuizSubmission.quiz_id == submission.quiz_id,
                                QuizSubmission.class_id == submission.class_id,
                                QuizSubmission.status.in_(
                                    [
                                        SubmissionStatus.submitted,
                                        SubmissionStatus.grading,
                                        SubmissionStatus.reviewed,
                                    ]
                                ),
                            )
                        )
                    ).scalar_one()
                    or 0
                )
                avg_row = (
                    await session.execute(
                        select(
                            func.coalesce(func.avg(QuizSubmission.final_score), 0.0),
                            func.coalesce(func.avg(QuizSubmission.accuracy_rate), 0.0),
                        ).where(
                            QuizSubmission.quiz_id == submission.quiz_id,
                            QuizSubmission.class_id == submission.class_id,
                            QuizSubmission.status.in_(
                                [
                                    SubmissionStatus.submitted,
                                    SubmissionStatus.grading,
                                    SubmissionStatus.reviewed,
                                ]
                            ),
                        )
                    )
                ).one()
                quiz_class_rel.target_student_count = target_student_count
                quiz_class_rel.submitted_student_count = submitted_student_count
                quiz_class_rel.submit_rate = (
                    round(submitted_student_count / target_student_count * 100, 2)
                    if target_student_count > 0
                    else 0.0
                )
                quiz_class_rel.avg_score = round(float(avg_row[0] or 0), 2)
                quiz_class_rel.avg_accuracy_rate = round(float(avg_row[1] or 0), 2)

            await session.commit()

    async def grade_submission(self, submission_id: int) -> tuple[bool, str]:
        """执行整份测验的 AI 批改。"""
        answer_ids = await self._load_submission_answer_ids(submission_id)
        if not answer_ids:
            await self._refresh_submission_summary(submission_id)
            return False, "当前测验暂无可批改答案"

        success_count = 0
        failure_messages: list[str] = []
        for answer_id in answer_ids:
            success, message = await self.grade_answer(answer_id)
            if success:
                success_count += 1
                continue
            failure_messages.append(f"answer_id={answer_id}: {message}")

        if failure_messages:
            return False, "; ".join(failure_messages)
        return True, f"AI 已完成 {success_count} 道题批改"

    async def _apply_grading_result(
        self,
        context: AnswerGradingContext,
        result: AIGradingResult,
    ) -> None:
        async with AsyncSessionLocal() as session:
            answer = await session.get(SubmissionAnswer, context.answer_id)
            if answer is None:
                return
            answer.grading_status = GradingStatus.graded
            answer.result_status = ResultStatus(result.result_status)
            answer.ai_score = result.ai_score
            answer.final_score = result.final_score
            answer.ai_feedback = result.ai_feedback
            session.add(
                AIGradingLog(
                    answer_id=context.answer_id,
                    model_name=result.model_name,
                    prompt_snapshot={
                        "question_content": context.question_content,
                        "reference_answer": context.reference_answer,
                        "question_type": context.question_type,
                        "full_score": context.full_score,
                    },
                    input_snapshot={
                        "student_answer": context.student_answer,
                        "image_urls": context.image_urls,
                    },
                    output_snapshot={
                        "raw_content": result.raw_content,
                        "ai_feedback": result.ai_feedback,
                        "typical_errors": [
                            item.model_dump() for item in result.typical_errors
                        ],
                    },
                    ai_result_status=result.result_status,
                    ai_score=result.ai_score,
                )
            )
            await session.commit()

        await self._upsert_typical_errors(
            answer_id=context.answer_id,
            question_id=context.question_id,
            typical_errors=result.typical_errors,
        )
        await self._refresh_submission_summary(context.submission_id)

    async def _record_failure(self, answer_id: int, error_message: str) -> None:
        async with AsyncSessionLocal() as session:
            answer = await session.get(SubmissionAnswer, answer_id)
            if answer is None:
                return
            answer.grading_status = GradingStatus.pending
            answer.ai_feedback = f"AI 批改失败：{error_message}"
            session.add(
                AIGradingLog(
                    answer_id=answer_id,
                    model_name="",
                    prompt_snapshot=None,
                    input_snapshot=None,
                    output_snapshot={"error": error_message},
                    ai_result_status="failed",
                    ai_score=0,
                )
            )
            await session.commit()

    async def grade_answer(self, answer_id: int) -> tuple[bool, str]:
        """执行单个答案的 AI 批改。"""
        context = await self._load_context(answer_id)
        if context is None:
            return False, "答案不存在"
        if not context.student_answer and not context.image_urls:
            return False, "答案为空，无需批改"

        await self._mark_answer_grading(answer_id)

        try:
            result = await ai_grading_service.grade_answer(
                question_content=context.question_content,
                reference_answer=context.reference_answer,
                student_answer=context.student_answer,
                question_type=context.question_type,
                full_score=context.full_score,
                question_image_urls=context.question_image_urls,
                image_urls=context.image_urls,
                known_typical_errors=context.known_typical_errors,
            )
            await self._apply_grading_result(context, result)
            return True, "AI 批改完成"
        except Exception as exc:
            logger.exception("AI 批改失败 answer_id={}", answer_id)
            await self._record_failure(answer_id, str(exc))
            await self._refresh_submission_summary(context.submission_id)
            return False, f"AI 批改失败：{exc}"


answer_grading_service = AnswerGradingService()
