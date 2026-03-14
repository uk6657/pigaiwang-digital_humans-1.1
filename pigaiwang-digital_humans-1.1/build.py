"""项目打包构建脚本

使用PyInstaller将编译后的Python代码打包成单个可执行文件。

该脚本会：
1. 检测已安装的模块
2. 切换到编译后的代码目录
3. 使用PyInstaller创建单文件可执行程序
4. 复制配置文件到输出目录
"""

import os
import pkgutil
import shutil
import site

import PyInstaller.__main__


def detect_installed_modules():
    """检测已安装的Python模块。

    Returns:
        list[str]: 已安装模块名称列表（排除PyInstaller自身）
    """
    modules = []
    for site_dir in site.getsitepackages():
        for _, name, _ in pkgutil.iter_modules([site_dir]):
            if name != "PyInstaller":
                modules.append(name)
    return modules


# 为每个包生成 --collect-all 参数
collect_list = [f"--collect-all={pkg}" for pkg in detect_installed_modules()]

# 获取原始脚本目录和 build 目录
script_dir = os.path.dirname(os.path.abspath(__file__))
build_dir = os.path.join(script_dir, "build/compiled")

# 切换到 build 目录（因为编译后的文件在这里）
os.chdir(build_dir)
print(f"当前工作目录: {os.getcwd()}")

# 定义输出路径（在 build 目录内）
dist_path = os.path.join(build_dir, "dist")
work_path = os.path.join(build_dir, "temp_build")

print(f"输出路径: {dist_path}")
print(f"临时工作路径: {work_path}")


# 清理旧的输出
if os.path.exists(dist_path):
    shutil.rmtree(dist_path)
if os.path.exists(work_path):
    shutil.rmtree(work_path)

# 打包参数
pyinstaller_args = [
    "main.py",  # build 目录中的 main.py（或 main.pyd）
    "--onefile",
    f"--paths={build_dir}",
    f"--distpath={dist_path}",
    f"--workpath={build_dir}",
    "--clean",
    # "--collect-all=app",
    "--add-binary=build/compiled/app:app",
] + collect_list

# 如果有其他资源文件也添加
# f"--add-data=static{os.pathsep}static"

# 执行打包
print("开始打包...")
PyInstaller.__main__.run(pyinstaller_args)

# 清理临时文件
if os.path.exists(work_path):
    shutil.rmtree(work_path)

exe_name = "main.exe" if os.name == "nt" else "main"
shutil.copytree("conf", "./dist/conf")
print("\n✅ 打包完成！")
print(f"📦 可执行文件: {os.path.join(dist_path, exe_name)}")
print("📁 所有编译后的代码和配置都已打包进单个文件")
