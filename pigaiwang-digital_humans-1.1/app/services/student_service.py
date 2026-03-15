"""Services for student accounts, tasks, and scripts."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import delete, select

from app.auth import jwt_manager
from app.common.time_ import time_now
from app.storage import (
    AsyncSessionLocal,
    GroupModel,
    StudentModel,
    StudentScriptModel,
    StudentTaskModel,
)
from app.utils.validation import validation_service


@dataclass(frozen=True)
class _SeedStudent:
    student_id: int
    group_id: int
    username: str
    password: str
    student_name: str


def _build_seed_students() -> tuple[_SeedStudent, ...]:
    students: list[_SeedStudent] = []
    mapping = {
        1001: range(11, 19),
        1002: range(21, 29),
        1003: range(31, 39),
        1004: range(41, 49),
    }
    for group_id, student_ids in mapping.items():
        for student_id in student_ids:
            students.append(
                _SeedStudent(
                    student_id=student_id,
                    group_id=group_id,
                    username=f"student{student_id}",
                    password="12345678",
                    student_name=f"name{student_id}",
                )
            )
    return tuple(students)


DEFAULT_STUDENTS = _build_seed_students()
VALID_GROUP_IDS = {1001, 1002, 1003, 1004}


class StudentService:
    """Student auth and task/script business logic."""

    async def bootstrap(self) -> None:
        """Ensure default student accounts exist."""

        await self.ensure_default_students()

    async def ensure_default_students(self) -> None:
        """Create seeded student accounts if they do not exist."""

        async with AsyncSessionLocal() as session:
            changed = False
            existing_students = {
                item.student_id: item
                for item in (await session.execute(select(StudentModel))).scalars().all()
            }
            for seed in DEFAULT_STUDENTS:
                student = existing_students.get(seed.student_id)

                if student is None:
                    session.add(
                        StudentModel(
                            student_id=seed.student_id,
                            group_id=seed.group_id,
                            username=seed.username,
                            password_hash=validation_service.get_hashed_password(seed.password),
                            student_name=seed.student_name,
                            is_active=True,
                        )
                    )
                    changed = True
                    continue

                if student.group_id != seed.group_id:
                    student.group_id = seed.group_id
                    changed = True
                if student.username != seed.username:
                    student.username = seed.username
                    changed = True
                if not validation_service.verify_password(seed.password, student.password_hash):
                    student.password_hash = validation_service.get_hashed_password(seed.password)
                    changed = True
                if not student.student_name:
                    student.student_name = seed.student_name
                    changed = True
                if not student.is_active:
                    student.is_active = True
                    changed = True

            if changed:
                await session.commit()

    @staticmethod
    def _serialize_student(student: StudentModel) -> dict:
        return {
            "student_id": str(student.student_id),
            "group_id": student.group_id,
            "username": student.username,
            "student_name": student.student_name,
        }

    async def login(
        self,
        username: str,
        password: str,
        device_id: str | None = None,
    ) -> tuple[bool, int, str, dict | None]:
        """Login a student."""

        await self.ensure_default_students()

        async with AsyncSessionLocal() as session:
            stmt = select(StudentModel).where(StudentModel.username == username)
            student = (await session.execute(stmt)).scalar_one_or_none()

            if student is None:
                return False, status.HTTP_400_BAD_REQUEST, "Username or password is incorrect", None

            if not student.is_active or student.is_deleted:
                return False, status.HTTP_403_FORBIDDEN, "Student account is disabled", None

            if not validation_service.verify_password(password, student.password_hash):
                return False, status.HTTP_400_BAD_REQUEST, "Username or password is incorrect", None

            token_info = await jwt_manager.generate_token(
                f"student:{student.student_id}",
                device_id=device_id,
                store_in_redis=False,
            )
            student.last_login_at = time_now()
            await session.commit()

            return (
                True,
                status.HTTP_200_OK,
                "Login successful",
                {
                    "user": self._serialize_student(student),
                    "token_info": token_info,
                },
            )

    async def get_student(self, student_id: int) -> StudentModel:
        """Load one student by id."""

        async with AsyncSessionLocal() as session:
            stmt = select(StudentModel).where(StudentModel.student_id == student_id)
            student = (await session.execute(stmt)).scalar_one_or_none()
            if student is None or student.is_deleted or not student.is_active:
                raise HTTPException(status_code=404, detail="Student not found")
            return student

    async def rename_student(self, student_id: int, student_name: str) -> dict:
        """Rename one student."""

        async with AsyncSessionLocal() as session:
            stmt = select(StudentModel).where(StudentModel.student_id == student_id)
            student = (await session.execute(stmt)).scalar_one_or_none()
            if student is None or student.is_deleted or not student.is_active:
                raise HTTPException(status_code=404, detail="Student not found")

            student.student_name = student_name
            await session.commit()
            return {
                "student_id": str(student.student_id),
                "student_name": student.student_name,
                "updated_at": student.updated_at,
            }

    async def save_task_script_batch(self, payload: dict) -> dict:
        """Replace all tasks and scripts using the submitted payload."""

        await self.ensure_default_students()
        tasks_payload = payload.get("tasks", [])
        scripts_payload = payload.get("scripts", {})

        async with AsyncSessionLocal() as session:
            groups = {
                item.id: item
                for item in (
                    await session.execute(select(GroupModel).where(GroupModel.id.in_(VALID_GROUP_IDS)))  # type: ignore[arg-type]
                ).scalars().all()
            }
            students = {
                item.student_id: item
                for item in (await session.execute(select(StudentModel))).scalars().all()
            }

            for group_payload in tasks_payload:
                group_id = int(group_payload["groupId"])
                if group_id not in VALID_GROUP_IDS or group_id not in groups:
                    raise HTTPException(status_code=400, detail=f"Invalid group id: {group_id}")

                groups[group_id].group_name = group_payload["groupName"]
                groups[group_id].description = group_payload["groupName"]

                seen_students: set[int] = set()
                for student_payload in group_payload.get("students", []):
                    student_id = int(student_payload["studentId"])
                    student = students.get(student_id)
                    if student is None:
                        raise HTTPException(status_code=400, detail=f"Invalid student id: {student_id}")
                    if student.group_id != group_id:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Student {student_id} does not belong to group {group_id}",
                        )
                    if student_id in seen_students:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Duplicate student task in group {group_id}: {student_id}",
                        )
                    student_name = student_payload["studentName"].strip()
                    if not student_name:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Student name is required for student {student_id}",
                        )
                    seen_students.add(student_id)

            for student_key, lines in scripts_payload.items():
                student_id = int(student_key)
                if student_id not in students:
                    raise HTTPException(status_code=400, detail=f"Invalid student id: {student_id}")
                orders = [int(line["order"]) for line in lines]
                if len(orders) != len(set(orders)):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Duplicate script order for student {student_id}",
                    )

            await session.execute(delete(StudentTaskModel))
            await session.execute(delete(StudentScriptModel))

            for group_payload in tasks_payload:
                group_id = int(group_payload["groupId"])
                for student_payload in group_payload.get("students", []):
                    student_id = int(student_payload["studentId"])
                    students[student_id].student_name = student_payload["studentName"].strip()
                    session.add(
                        StudentTaskModel(
                            group_id=group_id,
                            student_id=student_id,
                            task_content=student_payload["task"],
                        )
                    )

            for student_key, lines in scripts_payload.items():
                student_id = int(student_key)
                for line in lines:
                    session.add(
                        StudentScriptModel(
                            student_id=student_id,
                            script_order=int(line["order"]),
                            question=line["question"],
                            answer=line["answer"],
                        )
                    )

            await session.commit()

        return await self.get_full_task_script_payload()

    async def get_group_tasks(self, group_id: int) -> dict:
        """Return all tasks for one group."""

        if group_id not in VALID_GROUP_IDS:
            raise HTTPException(status_code=404, detail="Group not found")

        async with AsyncSessionLocal() as session:
            group = (
                await session.execute(select(GroupModel).where(GroupModel.id == group_id))
            ).scalar_one_or_none()
            if group is None or group.is_deleted or not group.is_active:
                raise HTTPException(status_code=404, detail="Group not found")

            students = (
                await session.execute(
                    select(StudentModel)
                    .where(StudentModel.group_id == group_id)
                    .order_by(StudentModel.student_id.asc())
                )
            ).scalars().all()
            tasks = {
                item.student_id: item
                for item in (
                    await session.execute(
                        select(StudentTaskModel).where(StudentTaskModel.group_id == group_id)
                    )
                ).scalars().all()
            }

            return {
                "groupId": group_id,
                "groupName": group.group_name,
                "students": [
                    {
                        "studentId": str(student.student_id),
                        "studentName": student.student_name,
                        "task": tasks[student.student_id].task_content if student.student_id in tasks else "",
                    }
                    for student in students
                ],
            }

    async def get_student_task(self, student_id: int) -> dict:
        """Return one student's task."""

        student = await self.get_student(student_id)
        async with AsyncSessionLocal() as session:
            group = (
                await session.execute(select(GroupModel).where(GroupModel.id == student.group_id))
            ).scalar_one_or_none()
            stmt = select(StudentTaskModel).where(StudentTaskModel.student_id == student_id)
            task = (await session.execute(stmt)).scalar_one_or_none()
            return {
                "groupId": student.group_id,
                "groupName": group.group_name if group is not None else "",
                "students": [
                    {
                        "studentId": str(student.student_id),
                        "studentName": student.student_name,
                        "task": task.task_content if task else "",
                    }
                ],
            }

    async def get_student_scripts(self, student_id: int) -> dict:
        """Return one student's ordered script."""

        student = await self.get_student(student_id)
        async with AsyncSessionLocal() as session:
            lines = (
                await session.execute(
                    select(StudentScriptModel)
                    .where(StudentScriptModel.student_id == student_id)
                    .order_by(StudentScriptModel.script_order.asc())
                )
            ).scalars().all()
            return {
                "studentId": str(student.student_id),
                "studentName": student.student_name,
                "scripts": [
                    {
                        "order": line.script_order,
                        "question": line.question,
                        "answer": line.answer,
                    }
                    for line in lines
                ],
            }

    async def get_full_task_script_payload(self) -> dict:
        """Return the full task/script payload currently stored."""

        async with AsyncSessionLocal() as session:
            groups = {
                item.id: item
                for item in (
                    await session.execute(
                        select(GroupModel).where(GroupModel.id.in_(VALID_GROUP_IDS))  # type: ignore[arg-type]
                    )
                ).scalars().all()
            }
            students = (
                await session.execute(
                    select(StudentModel).order_by(StudentModel.student_id.asc())
                )
            ).scalars().all()
            tasks_rows = (
                await session.execute(select(StudentTaskModel))
            ).scalars().all()
            script_rows = (
                await session.execute(
                    select(StudentScriptModel).order_by(
                        StudentScriptModel.student_id.asc(),
                        StudentScriptModel.script_order.asc(),
                    )
                )
            ).scalars().all()

            task_map = {item.student_id: item.task_content for item in tasks_rows}
            students_by_group: dict[int, list[StudentModel]] = {}
            for student in students:
                students_by_group.setdefault(student.group_id, []).append(student)

            tasks = []
            for group_id in sorted(VALID_GROUP_IDS):
                group = groups.get(group_id)
                if group is None:
                    continue
                tasks.append(
                    {
                        "groupId": group_id,
                        "groupName": group.group_name,
                        "students": [
                            {
                                "studentId": str(student.student_id),
                                "studentName": student.student_name,
                                "task": task_map.get(student.student_id, ""),
                            }
                            for student in students_by_group.get(group_id, [])
                        ],
                    }
                )

            student_name_map = {student.student_id: student.student_name for student in students}
            scripts: dict[str, list[dict]] = {}
            for row in script_rows:
                scripts.setdefault(str(row.student_id), []).append(
                    {
                        "order": row.script_order,
                        "question": row.question,
                        "answer": row.answer,
                    }
                )

            for student in students:
                scripts.setdefault(str(student.student_id), [])

            return {"tasks": tasks, "scripts": scripts}


student_service = StudentService()
