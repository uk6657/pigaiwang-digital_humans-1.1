"""管理员相关操作的返回校验"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.auth.jwt_manager import TokenInfo


class LoginResponseModel(BaseModel):
    user_id: str = Field(description="用户唯一ID")
    username: str = Field(description="用户名")
    token_info: TokenInfo = Field(
        description="jwt_token 信息，包含access_token 字段和 用户唯一ID"
    )

    model_config = ConfigDict(from_attributes=True)


class CodeImageResponseModel(BaseModel):
    code_image_id: str = Field(description="验证码图形ID")
    code_image_base64: str = Field(description="验证码图形")
    image_type: str = Field("image/png", description="图片类型")

    model_config = ConfigDict(from_attributes=True)


class AdminBoundRoleResponseModel(BaseModel):
    id: str = Field(..., description="角色唯一ID")
    role_name: str = Field(..., description="角色名称")
    description: str = Field(..., description="角色描述")

    model_config = ConfigDict(from_attributes=True)


class AdminResponseModel(BaseModel):
    id: str = Field(..., description="用户唯一ID")
    username: str = Field(..., description="用户名")
    phone: str = Field(..., description="用户绑定的手机号，会有+86前缀")
    status: int = Field(..., description="用户状态：0-被禁用，1-正常，2-待审核")
    created_at: datetime = Field(..., description="创建时间（北京时间）")
    updated_at: datetime = Field(..., description="更新时间（北京时间）")
    last_login_at: datetime | None = Field(None, description="最后登录时间")

    is_online: bool = Field(..., description="用户在线状态，True-在线，False-不在线")

    bound_roles: list[AdminBoundRoleResponseModel] = Field(
        ..., description="管理员已绑定角色列表"
    )

    model_config = ConfigDict(from_attributes=True)


class CheckingFieldsResponseModel(BaseModel):
    id: str = Field(description="用户唯一ID")
    company_name: str = Field(..., description="用户所在企业名称")
    credit_code: str = Field(..., description="企业统一社会信用代码")
    contact_person: str = Field(..., description="企业联系人")
    email: str = Field(..., description="企业邮箱")
    created_at: datetime = Field(..., description="创建时间（北京时间）")

    model_config = ConfigDict(from_attributes=True)


class ProjectResponseModel(BaseModel):
    id: str = Field(..., description="项目唯一ID")
    project_name: str = Field(..., description="项目名称")
    budget: Decimal = Field(..., description="最高限价")
    estimated_bidders: int | None = Field(None, description="预估投标单位数量")
    enterprise_level: str | None = Field(
        None, description="企业资质等级（如一级、特级）"
    )

    model_config = ConfigDict(from_attributes=True)


class CompanyResponseModel(BaseModel):
    id: str = Field(..., description="企业唯一ID")
    company_name: str | None = Field(None, description="用户所在企业名称")
    credit_code: str | None = Field(None, description="企业统一社会信用代码")
    contact_person: str | None = Field(None, description="企业联系人")
    email: str | None = Field(None, description="企业邮箱")

    model_config = ConfigDict(from_attributes=True)


class UserOrAdminResponseModel(BaseModel):
    id: str = Field(..., description="用户唯一ID")
    username: str = Field(..., description="用户名")
    phone: str = Field(..., description="用户绑定的手机号，会有+86前缀")
    status: int = Field(..., description="用户状态：0-被禁用，1-正常")
    created_at: datetime = Field(..., description="创建时间（北京时间）")
    updated_at: datetime = Field(..., description="更新时间（北京时间）")
    last_login_at: datetime | None = Field(None, description="最后登录时间")

    company: CompanyResponseModel | None = Field(None, description="用户所在企业信息")

    model_config = ConfigDict(from_attributes=True)


class TransactionRecordResponseModel(BaseModel):
    id: str = Field(..., description="交易记录 ID")
    user_id: str = Field(..., description="用户 ID")
    transaction_type: str | None = Field(None, description="充值、消费")
    payment_method: str | None = Field(
        None, description="交易来源，如 'wechat', 'alipay' 等（仅充值记录有）"
    )
    project_id: str | None = Field(None, description="项目 ID")
    service_type: str | None = Field(
        None, description="消费服务类型：高得分报价区间预测, 报价模拟分析等）"
    )
    amount: Decimal = Field(..., description="交易金额")
    balance_after: Decimal = Field(..., description="交易后余额")
    description: str = Field(..., description="交易描述")
    created_at: datetime = Field(..., description="记录创建时间")
    updated_at: datetime = Field(..., description="记录最后更新时间")

    user: UserOrAdminResponseModel = Field(..., description="该交易记录的关联用户")
    project: ProjectResponseModel | None = Field(
        None, description="该交易关联的项目, 可为None"
    )

    model_config = ConfigDict(from_attributes=True)


class AdminUserIDResponseModel(BaseModel):
    admin_user_ids: list[str] = Field(default=[], description="管理员用户ID列表")

    model_config = ConfigDict(from_attributes=True)


class ExportSystemLogFields(BaseModel):
    level: str = Field(..., description="日志级别")
    message: str | None = Field(None, description="日志消息")
    # created_at: datetime = Field(..., description="创建时间")

    model_config = ConfigDict(from_attributes=True)


systemLogEToC = {
    "level": "日志级别",
    "message": "日志消息",
    "created_at": "创建时间",
}


class ExportUserLogFields(BaseModel):
    level: str = Field(..., description="日志级别")
    message: str | None = Field(None, description="日志消息")
    # username: str | None = Field(None, description="操作人")
    # created_at: datetime = Field(..., description="创建时间")

    model_config = ConfigDict(from_attributes=True)


userLogEToC = {
    "level": "日志级别",
    "message": "日志消息",
    "username": "操作人",
    "created_at": "创建时间",
    "is_deleted": "该用户是否已被删除",
}


class TotalAmountResponseModel(BaseModel):
    total_consumed: Decimal = Field(..., description="消费总金额")
    total_recharged: Decimal = Field(..., description="充值总金额")

    model_config = ConfigDict(from_attributes=True)


class TransactionRecordFieldsByExported(BaseModel):
    # transaction_type: int = Field(..., description="交易类型：1-充值，2-消费")
    service_type: str | None = Field(
        None, description="服务类型：高得分报价区间预测, 报价模拟分析等"
    )
    # payment_method: str | None = Field(
    #     None, description="支付方式，如支付宝、微信、信用卡等"
    # )
    amount: Decimal = Field(..., description="交易金额（正数）")
    balance_after: Decimal = Field(..., description="交易后余额")
    description: str | None = Field(None, description="交易说明")
    # created_at: datetime = Field(..., description="创建时间")


class UserFieldsByExported(BaseModel):
    username: str = Field(..., description="用户名")
    # is_deleted: int = Field(..., description="是否被删除：0-未删除，1-已删除")


class CompanyFieldsByExported(BaseModel):
    company_name: str = Field(..., description="企业名称")
    credit_code: str = Field(..., description="统一社会信用代码")


class ProjectFieldsByExported(BaseModel):
    project_name: str = Field(..., description="项目名称")


class ExportAllTransactionsResponseModel(
    TransactionRecordFieldsByExported,
    UserFieldsByExported,
    CompanyFieldsByExported,
    ProjectFieldsByExported,
):
    pass


exportAllTransactionsFieldsEToC = {
    "transaction_type": "交易类型",
    "service_type": "服务类型",
    "payment_method": "支付方式",
    "amount": "交易金额（元）",
    "balance_after": "交易后余额（元）",
    "description": "交易说明",
    "created_at": "创建时间",
    "username": "用户名",
    "company_name": "企业名称",
    "credit_code": "统一社会信用代码",
    "project_name": "项目名称",
    "is_deleted": "该用户是否已被删除",
}


class OneDayRechargedAndConsumedStatisticResponseModel(BaseModel):
    amount_recharged: str | Decimal = Field(..., description="当天总充值金额")
    amount_simulate_consumed: str | Decimal = Field(
        ..., description="当天使用报价模拟分析服务的总消费金额"
    )
    amount_predict_consumed: str | Decimal = Field(
        ..., description="当天使用高得分报价区间预测服务的总消费金额"
    )

    model_config = ConfigDict(from_attributes=True)


class TargetYearEveryMonthConsumedStatisticResponseModel(BaseModel):
    amount_simulate: str | Decimal = Field(
        ...,
        description="目标年中，所有普通用户在某一个月使用报价模拟分析服务的总消费金额",
    )
    amount_predict: str | Decimal = Field(
        ...,
        description="目标年中，所有普通用户在某一个月使用高得分报价区间预测服务的总消费金额",
    )

    model_config = ConfigDict(from_attributes=True)


class TargetYearConsumedStatisticResponseModel(BaseModel):
    statistics_list: list[
        dict[str, TargetYearEveryMonthConsumedStatisticResponseModel]
    ] = Field(..., description="目标年中，每个月的消费统计数据")
    total_recharged: str | Decimal = Field(..., description="目标年中的总充值金额")

    model_config = ConfigDict(from_attributes=True)


class UserStatisticsResponseModel(BaseModel):
    amount_recharged: str | Decimal = Field(..., description="总充值金额")
    amount_simulate: str | Decimal = Field(
        ..., description="使用报价模拟分析服务的总消费金额"
    )
    amount_predict: str | Decimal = Field(
        ..., description="使用高得分报价区间预测服务的总消费金额"
    )

    model_config = ConfigDict(from_attributes=True)
