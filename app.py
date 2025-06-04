import streamlit as st
import pandas as pd
import re
import time
import urllib.parse
import asyncio
from playwright.async_api import async_playwright
import nest_asyncio
import traceback
import random
import json

# Enable nested event loops for Streamlit
nest_asyncio.apply()

# Set page config
st.set_page_config(
    page_title="LinkedIn Contact Scraper - Enhanced",
    page_icon="🔍",
    layout="wide"
)

# Initialize session state variables
if 'results' not in st.session_state:
    st.session_state.results = []
if 'scraping_in_progress' not in st.session_state:
    st.session_state.scraping_in_progress = False
if 'debug_info' not in st.session_state:
    st.session_state.debug_info = []

# App title and description
st.title("LinkedIn Contact Scraper (Enhanced Edition)")
st.markdown("""
Enhanced LinkedIn profile scraper with improved anti-detection and debugging capabilities.
**New Features**: Better stealth, multiple search engines, detailed debugging.
""")

# Status and progress placeholders
status_placeholder = st.empty()
progress_placeholder = st.empty()
debug_placeholder = st.empty()

# Sidebar for inputs
with st.sidebar:
    st.header("Search Parameters")
    keyword = st.text_input("Enter keyword to refine search:", placeholder="e.g. developer, CEO, marketing")
    pages_to_scrape = st.slider("Number of pages to scrape:", min_value=1, max_value=3, value=1)
    email_providers = st.multiselect(
        "Email providers to search for:",
        ["@gmail.com", "@yahoo.com", "@outlook.com", "@rediffmail.com", "@hotmail.com"],
        default=["@gmail.com", "@yahoo.com"]
    )
    
    # Search engine selection
    search_engine = st.selectbox("Search Engine:", ["Google", "Bing", "DuckDuckGo"], index=1)
    
    # Advanced options
    with st.expander("⚙️ Advanced Options"):
        browser_type = st.selectbox("Browser Engine:", ["chromium", "firefox", "webkit"], index=0)
        delay_between_requests = st.slider("Delay between requests (seconds):", 2, 15, 5)
        use_stealth_mode = st.checkbox("Enable stealth mode", value=True)
        block_images = st.checkbox("Block images (faster)", value=True)
        enable_debug = st.checkbox("Enable debug mode", value=True)
        simple_query = st.checkbox("Use simple query (less detection)", value=True)
    
    start_scraping = st.button("🚀 Start Scraping", type="primary", 
                              disabled=st.session_state.scraping_in_progress)

# Random user agents pool
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
]

def extract_emails(text):
    """Extract email addresses with improved filtering"""
    email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    emails = re.findall(email_regex, text)
    
    blocked_domains = [
        "licdn.com", "linkedin.com", "static", "cdn", "img", "facebook.com",
        "twitter.com", "instagram.com", "youtube.com", "example.com", "test.com",
        "localhost", "127.0.0.1", "noreply", "no-reply", "donotreply", "sentry.io"
    ]
    
    clean_emails = []
    for email in emails:
        email_lower = email.lower()
        if any(domain in email_lower for domain in blocked_domains):
            continue
        if any(word in email_lower for word in ['example', 'test', 'sample', 'dummy']):
            continue
        if len(email) < 5 or len(email) > 50:
            continue
        if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            clean_emails.append(email)
    
    return list(set(clean_emails))

def extract_phones(text):
    """Extract Indian phone numbers with better validation"""
    phone_patterns = [
        r"(?:\+91[-\s]?)?[6-9]\d{4}[-\s]?\d{5}",
        r"\+91[-\s]?[6-9]\d{9}",
        r"(?:\+91[-\s]?)?[6-9]\d[-\s]?\d{4}[-\s]?\d{4}",
    ]
    
    phones = []
    for pattern in phone_patterns:
        phones.extend(re.findall(pattern, text))
    
    clean_phones = []
    for phone in phones:
        digits_only = re.sub(r'\D', '', phone)
        if len(digits_only) == 10 and digits_only[0] in '6789':
            clean_phones.append(phone.strip())
        elif len(digits_only) == 12 and digits_only.startswith('91') and digits_only[2] in '6789':
            clean_phones.append(phone.strip())
    
    # Filter fake numbers
    fake_patterns = [
        r'1234567890', r'9876543210', r'0000000000', r'1111111111',
        r'2222222222', r'3333333333', r'4444444444', r'5555555555'
    ]
    
    filtered_phones = []
    for phone in list(set(clean_phones)):
        digits = re.sub(r'\D', '', phone)
        if not any(re.search(pattern, digits) for pattern in fake_patterns):
            if len(set(digits[-10:])) > 3:
                filtered_phones.append(phone)
    
    return filtered_phones

async def setup_playwright_browser(playwright, browser_type="chromium"):
    """Setup Playwright browser with enhanced anti-detection"""
    try:
        # Enhanced browser launch options
        launch_options = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--disable-blink-features=AutomationControlled",
                "--exclude-switches=enable-automation",
                "--disable-extensions",
                "--no-first-run",
                "--disable-default-apps",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--start-maximized"
            ]
        }
        
        # Launch browser
        if browser_type == "chromium":
            browser = await playwright.chromium.launch(**launch_options)
        elif browser_type == "firefox":
            browser = await playwright.firefox.launch(**launch_options)
        else:
            browser = await playwright.webkit.launch(**launch_options)
        
        # Create context with realistic settings
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": random.choice(USER_AGENTS),
            "locale": "en-US",
            "timezone_id": "America/New_York"
        }
        
        context = await browser.new_context(**context_options)
        
        # Block unnecessary resources
        if block_images:
            await context.route("**/*.{png,jpg,jpeg,gif,svg,webp,ico,woff,woff2}", 
                              lambda route: route.abort())
        
        page = await context.new_page()
        
        # Enhanced anti-detection measures
        if use_stealth_mode:
            await page.add_init_script("""
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                
                // Mock plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                
                // Mock languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                
                // Add chrome object
                window.chrome = {
                    runtime: {},
                };
                
                // Mock permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Hide automation indicators
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false,
                });
            """)
        
        status_placeholder.success("✅ Enhanced browser setup successful!")
        return browser, context, page
        
    except Exception as e:
        status_placeholder.error(f"❌ Error setting up browser: {str(e)}")
        return None, None, None

def build_search_query(keyword, email_providers, search_engine, simple_query=False):
    """Build search query based on engine and complexity"""
    if simple_query:
        # Simple query to avoid detection
        if search_engine == "Google":
            return f'site:linkedin.com/in/ {keyword}'
        elif search_engine == "Bing":
            return f'site:linkedin.com/in/ {keyword}'
        else:  # DuckDuckGo
            return f'site:linkedin.com/in/ {keyword}'
    else:
        # Complex query with email providers
        email_query = " OR ".join([f'"{provider}"' for provider in email_providers])
        if search_engine == "Google":
            return f'site:linkedin.com/in/ "{keyword}" ({email_query})'
        elif search_engine == "Bing":
            return f'site:linkedin.com/in/ {keyword} ({email_query})'
        else:  # DuckDuckGo
            return f'site:linkedin.com/in/ {keyword} email'

def get_search_url(query, search_engine):
    """Get search URL based on engine"""
    encoded_query = urllib.parse.quote_plus(query)
    
    if search_engine == "Google":
        return f"https://www.google.com/search?q={encoded_query}"
    elif search_engine == "Bing":
        return f"https://www.bing.com/search?q={encoded_query}"
    else:  # DuckDuckGo
        return f"https://duckduckgo.com/?q={encoded_query}"

def get_result_selectors(search_engine):
    """Get CSS selectors for each search engine"""
    if search_engine == "Google":
        return {
            "result": "div.tF2Cxc, div.g",
            "title": "h3",
            "link": "a",
            "next": "#pnnext"
        }
    elif search_engine == "Bing":
        return {
            "result": ".b_algo",
            "title": "h2 a",
            "link": "h2 a",
            "next": ".sb_pagN"
        }
    else:  # DuckDuckGo
        return {
            "result": "[data-testid='result']",
            "title": "h2 a span",
            "link": "h2 a",
            "next": ".sb_pagN"  # DDG doesn't have easy pagination
        }

async def debug_page_content(page, step_name):
    """Save page content for debugging"""
    if enable_debug:
        try:
            content = await page.content()
            title = await page.title()
            url = page.url
            
            debug_info = {
                "step": step_name,
                "title": title,
                "url": url,
                "content_length": len(content),
                "has_captcha": "captcha" in content.lower() or "unusual traffic" in content.lower(),
                "timestamp": time.strftime('%H:%M:%S')
            }
            
            st.session_state.debug_info.append(debug_info)
            
            # Save content to show user if needed
            if debug_info["has_captcha"]:
                with open(f"/tmp/debug_{step_name}.html", "w", encoding="utf-8") as f:
                    f.write(content)
                    
        except Exception as e:
            st.session_state.debug_info.append({
                "step": step_name,
                "error": str(e),
                "timestamp": time.strftime('%H:%M:%S')
            })

async def scrape_search_results(page, search_query, pages_to_scrape, search_engine):
    """Scrape search results with enhanced detection avoidance"""
    all_results = []
    selectors = get_result_selectors(search_engine)
    
    try:
        # Navigate to search engine
        search_url = get_search_url(search_query, search_engine)
        status_placeholder.info(f"🔍 Searching on {search_engine}: {search_query}")
        
        # Random delay before starting
        await page.wait_for_timeout(random.randint(2000, 5000))
        
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(3000, 7000))
        
        # Debug the initial page load
        await debug_page_content(page, "initial_search")
        
        # Check for blocking/CAPTCHA
        page_content = await page.content()
        if any(term in page_content.lower() for term in ["captcha", "unusual traffic", "blocked", "security check"]):
            status_placeholder.error(f"❌ {search_engine} detected automation. Try different engine or settings.")
            return []
        
        # Scraping loop
        for current_page in range(1, pages_to_scrape + 1):
            status_placeholder.info(f"📄 Scraping page {current_page} of {pages_to_scrape}")
            
            # Wait for results with multiple selectors
            result_found = False
            for selector in [selectors["result"], "div", "article"]:  # Fallback selectors
                try:
                    await page.wait_for_selector(selector, timeout=10000)
                    result_found = True
                    break
                except:
                    continue
            
            if not result_found:
                status_placeholder.warning(f"⚠️ No results container found on page {current_page}")
                await debug_page_content(page, f"no_results_page_{current_page}")
                break
            
            # Get search results
            results = await page.query_selector_all(selectors["result"])
            
            if not results:
                status_placeholder.warning(f"⚠️ No results on page {current_page}")
                await debug_page_content(page, f"empty_page_{current_page}")
                break
            
            status_placeholder.info(f"📊 Found {len(results)} results on page {current_page}")
            
            # Process each result
            for i, result in enumerate(results[:8]):  # Limit to avoid rate limits
                try:
                    # Try different ways to get title and link
                    title_elem = await result.query_selector(selectors["title"])
                    if not title_elem:
                        title_elem = await result.query_selector("h2, h3, .title, [role='heading']")
                    
                    link_elem = await result.query_selector(selectors["link"])
                    if not link_elem:
                        link_elem = await result.query_selector("a[href*='linkedin.com']")
                    
                    if not title_elem or not link_elem:
                        continue
                    
                    title = await title_elem.inner_text()
                    link = await link_elem.get_attribute("href")
                    
                    # Filter for LinkedIn profiles
                    if not link or "linkedin.com" not in link or "/in/" not in link:
                        continue
                    
                    status_placeholder.info(f"🔍 Processing: {title[:50]}...")
                    
                    # Open new tab for profile with random delay
                    await page.wait_for_timeout(random.randint(2000, 5000))
                    profile_page = await page.context.new_page()
                    
                    try:
                        await profile_page.goto(link, wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(random.randint(3000, 6000))
                        
                        # Simulate human behavior
                        await profile_page.evaluate("window.scrollTo(0, document.body.scrollHeight/3)")
                        await page.wait_for_timeout(random.randint(1000, 3000))
                        await profile_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(random.randint(2000, 4000))
                        
                        # Extract content
                        content = await profile_page.content()
                        
                        # Get additional data
                        try:
                            title_text = await profile_page.title()
                            content += f" {title_text}"
                        except:
                            pass
                        
                        emails = extract_emails(content)
                        phones = extract_phones(content)
                        
                        result_data = {
                            "Title": title,
                            "Link": link,
                            "Source": f"LinkedIn ({search_engine})",
                            "Emails": ", ".join(emails) if emails else "No emails found",
                            "Phones": ", ".join(phones) if phones else "No phones found",
                            "Email Count": len(emails),
                            "Phone Count": len(phones),
                            "Page": current_page
                        }
                        all_results.append(result_data)
                        
                        status_placeholder.success(f"✅ Found {len(emails)} emails, {len(phones)} phones")
                        
                    except Exception as e:
                        status_placeholder.warning(f"⚠️ Error loading profile: {str(e)[:100]}")
                    finally:
                        await profile_page.close()
                    
                    # Random delay between profiles
                    await page.wait_for_timeout(random.randint(3000, 8000))
                    
                except Exception as e:
                    status_placeholder.warning(f"⚠️ Error processing result {i+1}: {str(e)[:100]}")
                    continue
            
            # Try to go to next page (mainly for Google/Bing)
            if current_page < pages_to_scrape and search_engine != "DuckDuckGo":
                try:
                    next_button = await page.query_selector(selectors["next"])
                    if next_button:
                        await next_button.click()
                        await page.wait_for_timeout(random.randint(5000, 10000))
                    else:
                        status_placeholder.info("📄 No more pages available")
                        break
                except:
                    status_placeholder.info("📄 Could not navigate to next page")
                    break
        
        return all_results
        
    except Exception as e:
        status_placeholder.error(f"❌ Scraping error: {str(e)}")
        await debug_page_content(page, "error_state")
        return []

async def perform_scraping_async():
    """Main async scraping function"""
    if not keyword.strip():
        status_placeholder.error("❌ Please enter a keyword to search for.")
        return
    
    st.session_state.scraping_in_progress = True
    st.session_state.debug_info = []
    progress_bar = progress_placeholder.progress(0)
    
    async with async_playwright() as playwright:
        browser, context, page = await setup_playwright_browser(playwright, browser_type)
        
        if not browser:
            st.session_state.scraping_in_progress = False
            return
        
        try:
            # Build search query
            search_query = build_search_query(keyword, email_providers, search_engine, simple_query)
            
            # Perform scraping
            results = await scrape_search_results(page, search_query, pages_to_scrape, search_engine)
            
            # Update progress
            progress_bar.progress(1.0)
            
            if results:
                status_placeholder.success(f"✅ Scraping complete! Found {len(results)} profiles.")
                st.session_state.results = results
                display_results(results)
            else:
                status_placeholder.warning("⚠️ No results found. Check debug info below.")
                if enable_debug:
                    display_debug_info()
            
        except Exception as e:
            status_placeholder.error(f"❌ Error during scraping: {str(e)}")
            if enable_debug:
                display_debug_info()
        finally:
            await browser.close()
            st.session_state.scraping_in_progress = False

def display_results(results):
    """Display scraping results with metrics"""
    st.subheader("📊 Scraped Results")
    df = pd.DataFrame(results)
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Profiles", len(df))
    with col2:
        emails_found = df[df['Email Count'] > 0].shape[0]
        st.metric("Profiles with Emails", emails_found)
    with col3:
        phones_found = df[df['Phone Count'] > 0].shape[0]
        st.metric("Profiles with Phones", phones_found)
    with col4:
        both_found = df[(df['Email Count'] > 0) & (df['Phone Count'] > 0)].shape[0]
        st.metric("Complete Contacts", both_found)
    
    # Results table
    st.dataframe(df, use_container_width=True)
    
    # Download button
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download Results as CSV",
        data=csv,
        file_name=f"linkedin_contacts_{keyword}_{search_engine}_{time.strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

def display_debug_info():
    """Display debug information"""
    if st.session_state.debug_info:
        with st.expander("🐛 Debug Information", expanded=True):
            for info in st.session_state.debug_info:
                st.json(info)

def run_async_scraping():
    try:
        asyncio.run(perform_scraping_async())
    except RuntimeError as e:
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(perform_scraping_async())
            loop.run_until_complete(task)
        except Exception as inner_e:
         status_placeholder.error(f"❌ Async inner error:\n{traceback.format_exc()}")
    except Exception as e:
        status_placeholder.error(f"❌ Error: {str(e)}")
        st.session_state.scraping_in_progress = False

# Handle scraping button
if start_scraping and not st.session_state.scraping_in_progress:
    run_async_scraping()

# Show existing results
if st.session_state.results and not st.session_state.scraping_in_progress:
    display_results(st.session_state.results)

# Show debug info if available
if st.session_state.debug_info and enable_debug:
    display_debug_info()

# Sidebar tips
st.sidebar.markdown("---")
st.sidebar.header("🔧 Troubleshooting")
st.sidebar.markdown("""
**If getting "No results":**
1. Try **Bing** or **DuckDuckGo** first
2. Enable **simple query** mode
3. Use **debug mode** to see what's happening
4. Increase delays between requests
5. Try **Firefox** browser engine

**Red flags in debug:**
- "captcha" or "unusual traffic"
- Content length < 1000 chars
- Title contains "Access Denied"
""")

st.sidebar.markdown("---")
st.sidebar.header("⚡ Best Practices")
st.sidebar.markdown("""
- **Start small**: 1 page, simple query
- **Bing works better** than Google for automation
- **Firefox** often less detected than Chrome
- **High delays** = better success rate
- **Debug mode** shows you what went wrong
""")

st.markdown("---")
st.caption("⚠️ **Disclaimer**: Use responsibly and respect platform Terms of Service. For educational purposes only.")