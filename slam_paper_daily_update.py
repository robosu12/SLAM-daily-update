import os
import re
import time
import base64
import requests
from datetime import datetime
from pathlib import Path

# ===================== 配置参数 =====================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # GitHub PAT
REPO_OWNER = "robosu12"       # GitHub用户名
REPO_NAME = "SLAM-daily-update"              # 仓库名
SEARCH_KEYWORDS = ["SLAM", "Simultaneous Localization and Mapping"]
TARGET_CONF = ["icra", "iros", "ral", "tro"]  # 目标会议/期刊
PROCESSED_FILE = "processed_repos.txt"    # 已处理仓库记录
SKIP_EXISTED = True                       # 启用去重
ONLY_NEW_UPDATED = False                  # 仅处理近期更新
TABLE_HEADER = """| 标题 | 作者 | 会议/期刊 | 年份 | 代码仓库 | 论文链接 |
|------|------|-----------|------|----------|----------|"""
TABLE_TEMPLATE = "| {title} | {authors} | {conf} | {year} | [{repo}]({repo_url}) | [{paper}]({paper_url}) |"
# ===================================================

def github_api_request(url, params=None):
    """GitHub API请求（带异常处理）"""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response.status_code == 403:
            reset_time = int(response.headers.get("X-RateLimit-Reset", time.time()))
            raise Exception(f"API速率限制，重置时间: {datetime.fromtimestamp(reset_time)}")
        elif response.status_code == 404:
            print(f"仓库不存在: {url}")
            return None
        else:
            print(f"API请求失败: {str(e)}")
            return None
    except Exception as e:
        print(f"请求异常: {str(e)}")
        return None

def search_slam_repos():
    """搜索符合条件的GitHub仓库"""
    base_url = "https://api.github.com/search/repositories"
    query = (
        f"{' '.join(SEARCH_KEYWORDS)} "
        f"{' '.join(TARGET_CONF)} "
        "has:code in:description,topics "
        "-topic:documentation -topic:demo"
    )
    
    all_repos = []
    page = 1
    while True:
        params = {"q": query, "sort": "updated", "order": "desc", "per_page": 100, "page": page}
        data = github_api_request(base_url, params)
        if not data or not data.get("items"):
            break
            
        all_repos.extend(data["items"])
        print(f"已获取第{page}页，累计{len(all_repos)}个仓库")
        
        if len(data["items"]) < params["per_page"]:
            break
            
        page += 1
        time.sleep(1)  # 遵守API速率限制
    
    return all_repos

def load_processed_repos():
    """加载已处理仓库列表"""
    processed_path = Path(PROCESSED_FILE)
    if not processed_path.exists():
        return []
    
    try:
        with open(processed_path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"加载已处理仓库失败: {str(e)}")
        return []

def save_processed_repos(repos):
    """保存已处理仓库列表（去重存储）"""
    try:
        unique_repos = sorted(set(repos))
        with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(unique_repos))
        print(f"已保存{len(unique_repos)}个已处理仓库记录")
    except Exception as e:
        print(f"保存已处理仓库失败: {str(e)}")

def parse_readme(readme_content, repo_info):
    """从README解析论文元数据"""
    patterns = {
        "title": r"## 📄 论文标题\s*[:：]\s*([\s\S]+?)\s*(?=\n##|$)",
        "authors": r"## 👥 作者\s*[:：]\s*([\s\S]+?)\s*(?=\n##|$)",
        "conf": r"## 📅 会议/期刊\s*[:：]\s*([\s\S]+?)\s*(?=\n##|$)",
        "year": r"## 📆 发表年份\s*[:：]\s*(\d{4})\s*(?=\n##|$)",
        "paper": r"## 📜 论文链接\s*[:：]\s*([\s\S]+?)\s*(?=\n##|$)"
    }
    
    result = {}
    for key, pattern in patterns.items():
        try:
            match = re.search(pattern, readme_content, re.IGNORECASE)
            result[key] = match.group(1).strip() if match else "未提供"
        except Exception as e:
            print(f"解析{key}失败: {str(e)}")
            result[key] = "解析错误"
    
    # 自动推断会议类型
    if result["conf"] in ["未提供", "解析错误"]:
        desc_lower = (repo_info.get("description") or "").lower()
        for conf in TARGET_CONF:
            if conf in desc_lower:
                result["conf"] = conf.upper()
                break
        else:
            result["conf"] = "其他会议"
    
    return result

def update_readme_table(rows):
    """更新README中的论文表格"""
    try:
        readme_path = Path("README.md")
        content = ""
        
        if readme_path.exists():
            with open(readme_path, "r", encoding="utf-8") as f:
                content = f.read()
        
        # 定位表格位置
        start_idx = content.find(TABLE_HEADER)
        if start_idx == -1:
            # 添加新表格
            content = f"# SLAM开源论文合集\n\n## 最新开源论文\n{TABLE_HEADER}\n" + "\n".join(rows)
        else:
            # 更新现有表格
            end_idx = content.find("\n## ", start_idx)
            if end_idx == -1:
                end_idx = len(content)
            content = content[:start_idx] + TABLE_HEADER + "\n" + "\n".join(rows) + content[end_idx:]
        
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        print(f"README更新完成，添加{len(rows)}篇论文")
        return True
    except Exception as e:
        print(f"更新README失败: {str(e)}")
        return False

def main():
    # 1. 加载已处理仓库
    processed_repos = load_processed_repos()
    print(f"已加载{len(processed_repos)}个已处理仓库")
    
    # 2. 搜索新仓库
    print("搜索符合条件的新仓库...")
    all_repos = search_slam_repos()
    if not all_repos:
        print("未找到符合条件的仓库")
        return
    
    # 3. 过滤仓库（去重+时间过滤）
    new_repos = []
    for repo in all_repos:
        repo_fullname = repo["full_name"]
        
        # 跳过已处理的仓库
        if SKIP_EXISTED and repo_fullname in processed_repos:
            continue
            
        # 时间过滤（可选）
        if ONLY_NEW_UPDATED:
            updated_at = datetime.strptime(repo["updated_at"], "%Y-%m-%dT%H:%M:%SZ")
            if (datetime.now() - updated_at).days > 7:
                continue
                
        new_repos.append(repo)
    
    if not new_repos:
        print("无新仓库需要处理")
        return
    print(f"发现{len(new_repos)}个新仓库待处理")
    
    # 4. 处理新仓库
    table_rows = []
    processed_in_this_run = []
    for repo in new_repos[:50]:  # 限制50个防止超时
        repo_fullname = repo["full_name"]
        repo_url = repo["html_url"]
        
        try:
            # 获取仓库详情
            repo_detail = github_api_request(f"https://api.github.com/repos/{repo_fullname}")
            if not repo_detail:
                print(f"跳过无法获取详情的仓库: {repo_fullname}")
                continue
                
            # 获取README内容
            readme_content = ""
            default_branch = repo_detail.get("default_branch", "main")
            readme_resp = github_api_request(
                f"https://api.github.com/repos/{repo_fullname}/contents/README.md",
                {"ref": default_branch}
            )
            
            if readme_resp and "content" in readme_resp:
                readme_content = base64.b64decode(readme_resp["content"]).decode("utf-8")
            
            # 解析论文信息
            paper_info = parse_readme(readme_content, repo)
            
            # 生成表格行
            table_row = TABLE_TEMPLATE.format(
                title=paper_info["title"],
                authors=paper_info["authors"],
                conf=paper_info["conf"],
                year=paper_info["year"],
                repo=f"{repo_fullname}",
                repo_url=repo_url,
                paper=paper_info["paper"],
                paper_url=paper_info["paper"]
            )
            table_rows.append(table_row)
            processed_in_this_run.append(repo_fullname)
            print(f"成功处理: {repo_fullname} ({paper_info['conf']} {paper_info['year']})")
            
            time.sleep(0.5)  # 控制请求频率
            
        except Exception as e:
            print(f"处理仓库 {repo_fullname} 时出错: {str(e)}")
    
    # 5. 更新README和记录
    if table_rows:
        # 按年份降序排序
        table_rows.sort(key=lambda x: int(re.search(r"\d{4}", x).group()), reverse=True)
        
        if update_readme_table(table_rows):
            # 更新已处理记录
            new_processed = processed_repos + processed_in_this_run
            save_processed_repos(new_processed)
            print(f"已保存{len(processed_in_this_run)}个新处理记录")

if __name__ == "__main__":
    main()
