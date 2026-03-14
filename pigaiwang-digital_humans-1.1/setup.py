"""编译项目代码"""

import glob
import os
import shutil

from setuptools import find_packages, setup

# 改成（加上 try-except 或条件导入，避免类型检查器报错）
try:
    from Cython.Build import cythonize
except ImportError:
    cythonize = None  # 或根据你的实际需求处理
dist_path: str = "build/compiled"
licence_file: str = "licence_code.py"
replace_tuple: tuple[str, str] = ("# _check_license_()", "_check_license_()")


def find_pyx_files(directory):
    """查找所有需要编译的 Python 文件"""
    pyx_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".py") and "__pycache__" not in root:
                pyx_files.append(os.path.join(root, file))
    return pyx_files


def clean_c_files(directory):
    """清理生成的 C 文件"""
    c_files = glob.glob(os.path.join(directory, "**", "*.c"), recursive=True)
    for c_file in c_files:
        os.remove(c_file)


def add_init_files(directory):
    """递归添加 __init__.py 文件"""
    try:
        init_file_path = os.path.join(directory, "__init__.py")
        if not os.path.exists(init_file_path):
            open(init_file_path, "w").close()
            print(f"Created: {init_file_path}")

        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isdir(item_path):
                add_init_files(item_path)
    except Exception as e:
        print(f"Error processing {directory}: {e}")


def read_licence_code():
    """读取授权验证代码"""
    if not os.path.exists(licence_file):
        print(f"Warning: {licence_file} not found, skipping licence code injection")
        exit()
        return ""

    with open(licence_file, "r", encoding="utf-8") as f:
        return f.read().strip() + "\n\n"


def prepare_build_directories():
    """准备构建目录"""
    # 清理旧的 build 目录
    if os.path.exists("build"):
        shutil.rmtree("build")

    # 创建新的目录结构
    os.makedirs("build/temp", exist_ok=True)
    os.makedirs(dist_path, exist_ok=True)
    print(f"Created build directories: build/temp and {dist_path}")


def inject_licence_code(source_dir, target_dir, licence_code):
    """将源代码添加授权代码后复制到目标目录"""
    check_stats = {}  # 统计每个文件的校验点数量

    for root, dirs, files in os.walk(source_dir):
        # 计算相对路径
        rel_path = os.path.relpath(root, source_dir)
        target_root = os.path.join(target_dir, rel_path)

        # 创建目标目录
        os.makedirs(target_root, exist_ok=True)

        for file in files:
            if file.endswith(".py") and "__pycache__" not in root:
                source_file = os.path.join(root, file)
                target_file = os.path.join(target_root, file)

                # 读取原文件内容
                with open(source_file, "r", encoding="utf-8") as f:
                    original_code = f.read()

                # 替换注释的校验调用为实际调用
                modified_code = original_code.replace(*replace_tuple)

                # 统计这个文件中有多少处校验
                check_count = original_code.count("# _check_license_()")
                if check_count > 0:
                    # 使用相对于source_dir的路径作为key
                    relative_file_path = os.path.relpath(source_file, source_dir)
                    check_stats[relative_file_path] = check_count

                # 写入授权代码 + 修改后的代码
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(licence_code)
                    f.write(modified_code)
    return check_stats


def print_check_statistics(check_stats):
    """打印校验统计信息"""
    if not check_stats:
        print("\nNo license checks found in the code.")
        return

    print("\n" + "=" * 60)
    print("License Check Statistics:")
    print("=" * 60)

    total_checks = 0
    for file_path in sorted(check_stats.keys()):
        count = check_stats[file_path]
        total_checks += count
        print(f"  {file_path}: {count} check(s)")

    print("-" * 60)
    print(f"Total: {total_checks} license check(s) in {len(check_stats)} file(s)")
    print("=" * 60)


def copy_compiled_files(build_lib, dist_dir):
    """复制编译后的文件到 dist 目录"""
    if os.path.exists(build_lib):
        # 复制编译后的 .so 或 .pyd 文件
        for root, dirs, files in os.walk(build_lib):
            rel_path = os.path.relpath(root, build_lib)
            target_root = os.path.join(dist_dir, rel_path)
            os.makedirs(target_root, exist_ok=True)

            for file in files:
                if file.endswith((".so", ".pyd", ".py")):
                    source = os.path.join(root, file)
                    target = os.path.join(target_root, file)
                    shutil.copy2(source, target)
                    print(f"Copied compiled file: {file}")


def copy_project_files(dist_dir):
    """复制项目运行所需的文件到 dist 目录"""
    # 复制主入口文件
    if os.path.exists("main.py"):
        shutil.copy("main.py", os.path.join(dist_dir, "main.py"))
        print("Copied: main.py")

    # 复制配置文件夹
    if os.path.exists("conf"):
        conf_target = os.path.join(dist_dir, "conf")
        if os.path.exists(conf_target):
            shutil.rmtree(conf_target)
        shutil.copytree("conf", conf_target)
        print("Copied: conf directory")

    # 如果有其他需要复制的文件或文件夹，在这里添加
    # 例如：requirements.txt, README.md, etc.
    for item in ["requirements.txt"]:
        if os.path.exists(item):
            shutil.copy(item, os.path.join(dist_dir, item))
            print(f"Copied: {item}")


def main():
    """运行编译"""
    print("=" * 60)
    print("Starting build process...")
    print("=" * 60)

    # 步骤 1: 准备构建目录
    print("\n[Step 1] Preparing build directories...")
    prepare_build_directories()

    # 步骤 2: 读取授权代码
    print("\n[Step 2] Reading licence code...")
    licence_code = read_licence_code()

    # 步骤 3: 添加 __init__.py 文件
    print("\n[Step 3] Adding __init__.py files...")
    add_init_files("./app")

    # 步骤 4: 注入授权代码到临时目录
    print("\n[Step 4] Injecting licence code...")
    temp_app_dir = "build/temp/app"
    check_stats = inject_licence_code("./app", temp_app_dir, licence_code)

    # 步骤 5: 编译 Cython 代码
    print("\n[Step 5] Compiling Cython code...")
    build_lib = "build/temp/compiled"
    setup(
        ext_modules=cythonize(
            find_pyx_files(temp_app_dir),
            nthreads=4,
            compiler_directives={"language_level": "3"},
        ),
        packages=find_packages(where="build/temp"),
        package_dir={"": "build/temp"},
        extra_compile_args=["-O3"],
        extra_link_args=["-s"],
        script_args=["build_ext", "--build-lib", build_lib],
    )

    # 步骤 6: 复制编译结果到 dist 目录
    print("\n[Step 6] Copying compiled files to dist...")
    copy_compiled_files(build_lib, dist_path)

    # 步骤 7: 复制项目文件
    print("\n[Step 7] Copying project files...")
    copy_project_files(dist_path)

    # 步骤 8: 清理临时 C 文件
    print("\n[Step 8] Cleaning up temporary C files...")
    clean_c_files("build/temp")

    print("\n" + "=" * 60)
    print("Build completed successfully!")
    print(f"Compiled files are in: {dist_path}")
    print("=" * 60)

    # 打印校验统计信息
    print_check_statistics(check_stats)


if __name__ == "__main__":
    main()
