"""开发模式运行, 该模式下不会启动 ARQ 后台任务处理器进程"""

import uvicorn

from app.configs import base_configs
from app.main import app

if __name__ == "__main__":
    print(
        f"Starting server on http://{base_configs.PROJECT_HOST}:{base_configs.PROJECT_PORT}"
    )
    print(app.version)
    app.docs_url = "/docs"
    app.redoc_url = "/redoc"
    app.openapi_url = "/openapi.json"

    # 重新设置 OpenAPI schema
    app.setup()

    uvicorn.run(
        "dev:app",
        host=base_configs.PROJECT_HOST,
        port=base_configs.PROJECT_PORT,
        reload=True,
    )
