"""Response models for student and task APIs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.auth.jwt_manager import TokenInfo


class StudentSummaryResponseModel(BaseModel):
    """Student profile summary."""

    student_id: str = Field(description="Student id")
    group_id: int = Field(description="Group id")
    username: str = Field(description="Username")
    student_name: str = Field(description="Student name")

    model_config = ConfigDict(from_attributes=True)


class StudentLoginResponseModel(BaseModel):
    """Student login response."""

    user: StudentSummaryResponseModel = Field(description="Current student")
    token_info: TokenInfo = Field(description="Access token info")


class StudentTaskItemResponseModel(BaseModel):
    """Task item for one student."""

    studentId: str = Field(description="Student id")
    studentName: str = Field(description="Student name")
    task: str = Field(description="Task content")


class GroupTaskResponseModel(BaseModel):
    """All student tasks for one group."""

    groupId: int = Field(description="Group id")
    groupName: str = Field(description="Group name")
    students: list[StudentTaskItemResponseModel] = Field(description="Student task list")


class StudentScriptLineResponseModel(BaseModel):
    """One student script line."""

    order: int = Field(description="Order in script")
    question: str = Field(description="Question")
    answer: str = Field(description="Answer")


class StudentScriptsResponseModel(BaseModel):
    """All script lines for one student."""

    studentId: str = Field(description="Student id")
    studentName: str = Field(description="Student name")
    scripts: list[StudentScriptLineResponseModel] = Field(description="Ordered script lines")


class TaskScriptBatchResponseModel(BaseModel):
    """Full saved task/script payload response."""

    tasks: list[GroupTaskResponseModel] = Field(description="Saved group tasks")
    scripts: dict[str, list[StudentScriptLineResponseModel]] = Field(
        description="Saved scripts keyed by student id"
    )


class StudentRenameResponseModel(BaseModel):
    """Student rename response."""

    student_id: str = Field(description="Updated student id")
    student_name: str = Field(description="Updated student name")
    updated_at: datetime = Field(description="Update time")
