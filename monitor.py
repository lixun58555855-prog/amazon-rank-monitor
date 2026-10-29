import json
import os
import re
import sys
import time
import urllib.parse
from playwright.sync_api import sync_playwright
from amazoncaptcha import AmazonCaptcha

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if not os.path.exists(config_path):
        print(f"❌ 找不到配置文件: {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def handle_captcha_if_needed(page, max_retries=3):
    """检测并使用 amazoncaptcha 自动破解亚马逊 Robot Check 验证码"""
    for attempt in range(1, max_retries + 1):
        title = page.title()
        captcha_form = page.query_selector('form[action*="validateCaptcha"]')
        captcha_input = page.query_selector('input#captchacharacters')
        is_robot_check = "Robot Check" in title or "CAPTCHA" in title.upper()
        
        if not (captcha_form or captcha_input or is_robot_check):
            return True

        input_elem = captcha_input or page.query_selector('input[type="text"]')
        if not input_elem:
            return True

        print(f"⚠️ [尝试 {attempt}/{max_retries}] 命中亚马逊验证码(Robot Check: {title})，正在自动破解...")
        
        img_element = page.query_selector('div.a-box-inner img') or page.query_selector('form img') or page.query_selector('img[src*="captcha"]')
        if not img_element:
            print("❌ 未能定位验证码图片元素")
            return False

        img_url = img_element.get_attribute('src')
        if not img_url:
            print("❌ 验证码图片链接为空")
            return False

        solution = AmazonCaptcha.fromlink(img_url).solve()
        print(f"💡 验证码识别结果: {solution}")

        if not solution or solution.strip() == "" or solution == "Not solved":
            print("❌ 验证码识别失败，重试中...")
            page.reload()
            page.wait_for_timeout(2000)
            continue

        input_elem.fill(solution)
        
        submit_btn = page.query_selector('button[type="submit"]') or page.query_selector('button.a-button-text')
        if submit_btn:
            submit_btn.click()
        else:
            page.keyboard.press('Enter')

        page.wait_for_load_state('domcontentloaded')
        page.wait_for_timeout(3000)

    if "Robot Check" in page.title() or page.query_selector('input#captchacharacters'):
        print("❌ 连续破解验证码失败，页面仍处于拦截状态！")
        return False
    
    print("✅ 验证码破盾成功，已进入页面！")
    return True

def switch_location_zip(page, city_name, zip_code):
    """
    智能切换指定城市的邮编，并在页面中验证生效状态
    """
    print(f"\n📍 [城市切换] 准备切换至: {city_name} (邮编: {zip_code}) ...")
    try:
        # 回到顶部，确保顶部导航栏完全在可视区
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)

        # 1. 检查顶部导航栏当前的配送地址
        loc_slot = page.query_selector('#nav-global-location-slot') or page.query_selector('#glow-ingress-line2')
        if loc_slot:
            current_text = loc_slot.inner_text().strip()
            clean_zip = zip_code.replace(" ", "").upper()
            clean_text = current_text.replace(" ", "").upper()
            if clean_zip in clean_text:
                print(f"  ✅ 当前已是目标邮编: {current_text}，无需重复切换")
                return True

        # 2. 点击配送地址触发弹出层 (使用 force=True 规避滚动遮挡)
        trigger_selector = '#nav-global-location-slot' if page.query_selector('#nav-global-location-slot') else '#glow-ingress-line2'
        page.click(trigger_selector, force=True, timeout=6000)
        page.wait_for_timeout(1500)

        # 3. 等待弹出层渲染
        zip_input = page.query_selector('#GLUXZipUpdateInput') or page.query_selector('#GLUXZipUpdateInput_0') or page.query_selector('input[aria-label*="zip" i]') or page.query_selector('input[aria-label*="postal" i]')
        
        if not zip_input:
            print("  ⚠️ 弹窗中未找到邮编输入框，可能属于多国家选择模式")
            close_btn = page.query_selector('button[name="glowDoneButton"]') or page.query_selector('.a-popover-header button')
            if close_btn:
                close_btn.click(force=True, timeout=3000)
            return False

        zip_input.fill("")
        zip_input.fill(zip_code)
        page.wait_for_timeout(500)

        # 4. 点击 Apply / 更新 按钮
        apply_btn = page.query_selector('#GLUXZipUpdate') or page.query_selector('input[aria-labelledby="GLUXZipUpdate-announce"]') or page.query_selector('#GLUXZipUpdate input')
        if apply_btn:
            apply_btn.click(force=True, timeout=4000)
        else:
            zip_input.press("Enter")
        page.wait_for_timeout(2000)

        # 5. 点击 Done / Continue 确认按钮
        done_btn = page.query_selector('button[name="glowDoneButton"]') or page.query_selector('.a-popover-footer button') or page.query_selector('#GLUXConfirmClose')
        if done_btn:
            try:
                done_btn.click(force=True, timeout=3000)
            except Exception:
                pass
        
        page.wait_for_load_state('domcontentloaded')
        page.wait_for_timeout(2500)

        # 6. 验证切换后结果
        loc_slot_after = page.query_selector('#nav-global-location-slot') or page.query_selector('#glow-ingress-line2')
        after_text = loc_slot_after.inner_text().strip() if loc_slot_after else "未知"
        print(f"  🎉 邮编设置完成，当前配送定位显示为: 【{after_text.replace(chr(10), ' ')}】")
        return True
    except Exception as e:
        print(f"  ⚠️ 切换邮编发生异常: {e}")
        # 如果卡住弹窗，强制按一次 Escape 键
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return False

def parse_search_page(page, target_asins, page_num):
    """解析当前搜索页，识别广告位(Sponsored)与自然位(Organic)"""
    results = []
    
    items = page.query_selector_all('div[data-component-type="s-search-result"]')
    if not items:
        items = page.query_selector_all('div.s-result-item[data-asin]')

    page_organic_idx = 0
    page_sponsored_idx = 0

    for item in items:
        asin = item.get_attribute('data-asin')
        if not asin or asin.strip() == "":
            continue

        item_text = item.inner_text()
        is_sponsored = False
        
        if "Sponsored" in item_text or "赞助商" in item_text or "Gesponsert" in item_text or "スポンサー" in item_text:
            is_sponsored = True
        elif item.query_selector('.s-sponsored-label-info-icon') or item.query_selector('span:has-text("Sponsored")'):
            is_sponsored = True

        if is_sponsored:
            page_sponsored_idx += 1
            current_type = "Sponsored (广告位)"
            current_rank = page_sponsored_idx
        else:
            page_organic_idx += 1
            current_type = "Organic (自然位)"
            current_rank = page_organic_idx

        # 如果属于我们要监控的目标 ASIN
        if asin in target_asins:
            title_elem = item.query_selector('h2 a span') or item.query_selector('h2')
            title = title_elem.inner_text().strip() if title_elem else "N/A"
            if len(title) > 30:
                title = title[:30] + "..."

            price_elem = item.query_selector('span.a-price span.a-offscreen')
            price = price_elem.inner_text().strip() if price_elem else "N/A"

            results.append({
                "asin": asin,
                "title": title,
                "price": price,
                "page": page_num,
                "type": current_type,
                "rank_in_page": current_rank
            })

    return results

def run_monitor():
    config = load_config()
    marketplaces = config.get("marketplaces", [])

    all_records = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-infobars',
            ]
        )

        for mp in marketplaces:
            if not mp.get("enabled", True):
                print(f"⏩ 站点已禁用跳过: {mp.get('name')}")
                continue

            site_code = mp.get("site", "US")
            site_name = mp.get("name", site_code)
            base_url = mp.get("base_url", "https://www.amazon.com").rstrip("/")
            locations = mp.get("locations", [{"city": "Default", "zip": "90001"}])
            max_pages = mp.get("max_pages", 2)
            targets = mp.get("targets", [])

            print(f"\n=======================================================")
            print(f"🌍 开始监控站点: 【{site_name} ({site_code})】 - {base_url}")
            print(f"=======================================================")

            # 为每个站点创建独立的 Browser Context
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                locale="en-US" if site_code == "US" else ("en-GB" if site_code == "UK" else "de-DE"),
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "accept-language": "en-US,en;q=0.9",
                    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "upgrade-insecure-requests": "1",
                }
            )
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)

            page = context.new_page()

            # 首次访问站点首页建立 Session
            try:
                page.goto(base_url, wait_until="domcontentloaded", timeout=35000)
                handle_captcha_if_needed(page)
            except Exception as e:
                print(f"⚠️ 首页初始化异常: {e}")

            # 遍历该站点下的各热门城市邮编
            for loc in locations:
                city = loc.get("city", "未知城市")
                zip_code = loc.get("zip", "")
                
                # 切换至目标城市邮编
                if zip_code:
                    switch_location_zip(page, city, zip_code)
                    handle_captcha_if_needed(page)

                # 遍历目标关键词
                for target in targets:
                    keyword = target["keyword"]
                    target_asins = set(target["asins"])
                    note = target.get("note", "")

                    print(f"\n  🎯 [{city} | {zip_code}] 检索词: 【{keyword}】 (目标 ASIN: {list(target_asins)})")
                    found_items = []

                    for page_num in range(1, max_pages + 1):
                        encoded_kw = urllib.parse.quote_plus(keyword)
                        search_url = f"{base_url}/s?k={encoded_kw}&page={page_num}"
                        
                        if page_num == 1:
                            search_box = page.query_selector('input#twotabsearchtextbox')
                            if search_box:
                                search_box.fill("")
                                search_box.fill(keyword)
                                search_box.press('Enter')
                                page.wait_for_load_state('domcontentloaded')
                            else:
                                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                        else:
                            next_btn = page.query_selector('a.s-pagination-next') or page.query_selector('a:has-text("Next")')
                            if next_btn:
                                next_btn.click()
                                page.wait_for_load_state('domcontentloaded')
                            else:
                                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

                        handle_captcha_if_needed(page)

                        if "Sorry! Something went wrong!" in page.title():
                            print("    ⚠️ 遇到 503 拦截，重载中...")
                            page.wait_for_timeout(2000)
                            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                            handle_captcha_if_needed(page)

                        page.mouse.wheel(0, 1500)
                        page.wait_for_timeout(1200)

                        matches = parse_search_page(page, target_asins, page_num)
                        for m in matches:
                            m["site"] = site_name
                            m["city"] = city
                            m["zip"] = zip_code
                            m["keyword"] = keyword
                            m["note"] = note
                            found_items.append(m)
                            print(f"    👉 命中! ASIN: {m['asin']} | {m['type']} #第{m['rank_in_page']}位 (第{page_num}页) | 价格: {m['price']}")

                        time.sleep(1.5)

                    # 补齐未进入监控范围的 ASIN
                    found_asins = {m["asin"] for m in found_items}
                    for missed in target_asins - found_asins:
                        found_items.append({
                            "site": site_name,
                            "city": city,
                            "zip": zip_code,
                            "keyword": keyword,
                            "asin": missed,
                            "title": "未进入监控范围",
                            "price": "-",
                            "page": f"> {max_pages}",
                            "type": "未上榜",
                            "rank_in_page": "-",
                            "note": note
                        })

                    all_records.extend(found_items)

            context.close()

        browser.close()

    # 输出结构化报告
    generate_reports(all_records)

def generate_reports(records):
    """生成结构化报告，包括城市横向对比透视表"""
    output_file = "rank_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    # 1. 明细流水表格
    detail_headers = ["站点", "城市/邮编", "关键词", "ASIN", "类型", "页码", "位次", "价格", "备注"]
    detail_rows = []
    for r in records:
        loc_str = f"{r['city']} ({r['zip']})" if r.get('zip') else r['city']
        detail_rows.append([
            r["site"],
            loc_str,
            r["keyword"],
            f"`{r['asin']}`",
            r["type"],
            f"第 {r['page']} 页" if str(r['page']).isdigit() else str(r['page']),
            f"#{r['rank_in_page']}" if str(r['rank_in_page']).isdigit() else str(r['rank_in_page']),
            r.get("price", "-"),
            r.get("note", "")
        ])

    detail_table = "| " + " | ".join(detail_headers) + " |\n"
    detail_table += "| " + " | ".join(["---"] * len(detail_headers)) + " |\n"
    for row in detail_rows:
        detail_table += "| " + " | ".join(row) + " |\n"

    # 2. 核心价值：多城市横向对比透视表 (Cross-City Comparison)
    # 获取所有的城市列表
    cities = sorted(list({f"{r['city']} ({r['zip']})" for r in records}))
    # 分组 key: (site, keyword, asin)
    pivot_data = {}
    for r in records:
        key = (r["site"], r["keyword"], r["asin"])
        if key not in pivot_data:
            pivot_data[key] = {}
        city_label = f"{r['city']} ({r['zip']})"
        if r["type"] == "未上榜":
            rank_str = "❌ 未上榜"
        else:
            prefix = "Ad" if "Sponsored" in r["type"] else "Nat"
            rank_str = f"{prefix} P{r['page']}#{r['rank_in_page']}"
        
        # 允许同一个城市下既有广告位又有自然位
        if city_label in pivot_data[key]:
            pivot_data[key][city_label] += f" / {rank_str}"
        else:
            pivot_data[key][city_label] = rank_str

    pivot_headers = ["站点", "关键词", "目标 ASIN"] + cities
    pivot_rows = []
    for (site, kw, asin), city_ranks in pivot_data.items():
        row = [site, kw, f"`{asin}`"]
        for c in cities:
            row.append(city_ranks.get(c, "-"))
        pivot_rows.append(row)

    pivot_table = "| " + " | ".join(pivot_headers) + " |\n"
    pivot_table += "| " + " | ".join(["---"] * len(pivot_headers)) + " |\n"
    for row in pivot_rows:
        pivot_table += "| " + " | ".join(row) + " |\n"

    # 打印到控制台
    print("\n==================== 📊 多城市排名对比透视看板 ====================")
    print(pivot_table)
    print("\n==================== 📋 详细抓取数据清单 ====================")
    print(detail_table)

    # 写入 GitHub Actions Step Summary
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("## 🚀 亚马逊 ASIN 多站点/多城市关键词排名监控看板\n\n")
            f.write(f"> 运行时间: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n\n")
            f.write("### 🌐 多城市分仓排名横向透视对比 (Cross-City Comparison)\n")
            f.write("*注：`Ad` 表示 Sponsored 广告位，`Nat` 表示 Organic 自然位，如 `Ad P1#2` 代表第1页第2位广告*\n\n")
            f.write(pivot_table)
            f.write("\n\n### 📋 完整数据明细\n\n")
            f.write(detail_table)
            f.write("\n\n---\n*监控引擎: Playwright 智能邮编注入 + amazoncaptcha 破盾*\n")

if __name__ == "__main__":
    run_monitor()
