import streamlit as st
import pandas as pd
import re
import time
import urllib.parse
import asyncio
from playwright.async_api import async_playwright
import nest_asyncio

# Enable nested event loops for Streamlit
nest_asyncio.apply()

# Set page config
st.set_page_config(
    page_title="LinkedIn Contact Scraper - Playwright",
    page_icon="🔍",
    layout="wide"
)

# Initialize session state variables
if 'results' not in st.session_state:
    st.session_state.results = []
if 'scraping_in_progress' not in st.session_state:
    st.session_state.scraping_in_progress = False

# App title and description
st.title("LinkedIn Contact Scraper (Playwright Edition)")
st.markdown("""
Enhanced LinkedIn profile scraper using Playwright for better reliability and stealth.
**Features**: Anti-detection, faster performance, better JavaScript handling.
""")

# Status and progress placeholders
status_placeholder = st.empty()
progress_placeholder = st.empty()

# Sidebar for inputs
with st.sidebar:
    st.header("Search Parameters")
    keyword = st.text_input("Enter keyword to refine search:", placeholder="e.g. developer, CEO, marketing")
    pages_to_scrape = st.slider("Number of pages to scrape:", min_value=1, max_value=5, value=2)
    email_providers = st.multiselect(
        "Email providers to search for:",
        ["@gmail.com", "@yahoo.com", "@outlook.com", "@rediffmail.com", "@hotmail.com"],
        default=["@gmail.com", "@yahoo.com", "@outlook.com"]
    )
    
    # Advanced options
    with st.expander("⚙️ Advanced Options"):
        browser_type = st.selectbox("Browser Engine:", ["chromium", "firefox", "webkit"], index=0)
        delay_between_requests = st.slider("Delay between requests (seconds):", 1, 10, 3)
        use_stealth_mode = st.checkbox("Enable stealth mode", value=True)
        block_images = st.checkbox("Block images (faster)", value=True)
        custom_user_agent = st.text_input("Custom User Agent (optional):", 
                                        placeholder="Leave empty for random")
    
    start_scraping = st.button("🚀 Start Scraping", type="primary", 
                              disabled=st.session_state.scraping_in_progress)

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
    """Setup Playwright browser with anti-detection"""
    try:
        # Browser launch options
        launch_options = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--window-size=1920,1080"
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
            "user_agent": custom_user_agent if custom_user_agent else 
                         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        context = await browser.new_context(**context_options)
        
        # Block images if requested
        if block_images:
            await context.route("**/*.{png,jpg,jpeg,gif,svg,webp}", lambda route: route.abort())
        
        page = await context.new_page()
        
        # Anti-detection measures
        if use_stealth_mode:
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
                
                window.chrome = {
                    runtime: {},
                };
            """)
        
        status_placeholder.success("✅ Playwright browser setup successful!")
        return browser, context, page
        
    except Exception as e:
        status_placeholder.error(f"❌ Error setting up browser: {str(e)}")
        return None, None, None

async def scrape_search_results(page, search_query, pages_to_scrape):
    """Scrape Google search results with Playwright"""
    all_results = []
    
    try:
        # Navigate to Google
        encoded_query = urllib.parse.quote_plus(search_query)
        google_url = f"https://www.google.com/search?q={encoded_query}"
        
        status_placeholder.info(f"🔍 Searching: {search_query}")
        
        await page.goto(google_url, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        
        # Check for CAPTCHA
        page_content = await page.content()
        if "captcha" in page_content.lower() or "unusual traffic" in page_content.lower():
            status_placeholder.error("❌ CAPTCHA detected. Try again later.")
            return []
        
        # Scraping loop
        for current_page in range(1, pages_to_scrape + 1):
            status_placeholder.info(f"📄 Scraping page {current_page} of {pages_to_scrape}")
            
            # Wait for results to load
            await page.wait_for_selector("div.tF2Cxc", timeout=10000)
            
            # Get search results
            results = await page.query_selector_all("div.tF2Cxc")
            
            if not results:
                status_placeholder.warning(f"⚠️ No results on page {current_page}")
                break
            
            # Process each result
            for i, result in enumerate(results[:5]):
                try:
                    title_elem = await result.query_selector("h3")
                    link_elem = await result.query_selector("a")
                    
                    if not title_elem or not link_elem:
                        continue
                    
                    title = await title_elem.inner_text()
                    link = await link_elem.get_attribute("href")
                    
                    if not link or "linkedin.com" not in link:
                        continue
                    
                    status_placeholder.info(f"🔍 Processing: {title[:50]}...")
                    
                    # Open new tab for profile
                    profile_page = await page.context.new_page()
                    
                    try:
                        await profile_page.goto(link, wait_until="networkidle", timeout=30000)
                        await profile_page.wait_for_timeout(3000)
                        
                        # Scroll to load dynamic content
                        await profile_page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await profile_page.wait_for_timeout(2000)
                        
                        # Extract content
                        content = await profile_page.content()
                        
                        # Try to get additional structured data
                        try:
                            title_text = await profile_page.title()
                            meta_desc = await profile_page.get_attribute("meta[name='description']", "content")
                            if meta_desc:
                                content += f" {title_text} {meta_desc}"
                        except:
                            pass
                        
                        emails = extract_emails(content)
                        phones = extract_phones(content)
                        
                        result_data = {
                            "Title": title,
                            "Link": link,
                            "Source": "LinkedIn",
                            "Emails": ", ".join(emails) if emails else "No emails found",
                            "Phones": ", ".join(phones) if phones else "No phones found",
                            "Email Count": len(emails),
                            "Phone Count": len(phones),
                            "Page": current_page
                        }
                        all_results.append(result_data)
                        
                    except Exception as e:
                        status_placeholder.warning(f"⚠️ Error loading profile: {str(e)[:100]}")
                    finally:
                        await profile_page.close()
                    
                    # Delay between requests
                    await page.wait_for_timeout(delay_between_requests * 1000)
                    
                except Exception as e:
                    status_placeholder.warning(f"⚠️ Error processing result {i+1}: {str(e)[:100]}")
                    continue
            
            # Try to go to next page
            if current_page < pages_to_scrape:
                try:
                    next_button = await page.query_selector("#pnnext")
                    if next_button:
                        await next_button.click()
                        await page.wait_for_timeout(3000)
                    else:
                        status_placeholder.info("📄 No more pages available")
                        break
                except:
                    status_placeholder.info("📄 Could not navigate to next page")
                    break
        
        return all_results
        
    except Exception as e:
        status_placeholder.error(f"❌ Scraping error: {str(e)}")
        return []

async def perform_scraping_async():
    """Main async scraping function"""
    if not keyword.strip():
        status_placeholder.error("❌ Please enter a keyword to search for.")
        return
    
    st.session_state.scraping_in_progress = True
    progress_bar = progress_placeholder.progress(0)
    
    async with async_playwright() as playwright:
        browser, context, page = await setup_playwright_browser(playwright, browser_type)
        
        if not browser:
            st.session_state.scraping_in_progress = False
            return
        
        try:
            # Build search query
            email_query = " OR ".join([f'"{provider}"' for provider in email_providers])
            search_query = f'site:linkedin.com/in/ "{keyword}" ({email_query}) "+91"'
            
            # Perform scraping
            results = await scrape_search_results(page, search_query, pages_to_scrape)
            
            # Update progress
            progress_bar.progress(1.0)
            
            if results:
                status_placeholder.success(f"✅ Scraping complete! Found {len(results)} profiles.")
                st.session_state.results = results
                
                # Display results
                display_results(results)
            else:
                status_placeholder.warning("⚠️ No results found. Try different keywords.")
            
        except Exception as e:
            status_placeholder.error(f"❌ Error during scraping: {str(e)}")
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
        file_name=f"linkedin_contacts_{keyword}_{time.strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

def run_async_scraping():
    """Wrapper to run async function in Streamlit"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(perform_scraping_async())
    except Exception as e:
        status_placeholder.error(f"❌ Async error: {str(e)}")
        st.session_state.scraping_in_progress = False

# Handle scraping button
if start_scraping and not st.session_state.scraping_in_progress:
    run_async_scraping()

# Show existing results
if st.session_state.results and not st.session_state.scraping_in_progress:
    st.subheader("📊 Previous Results")
    df = pd.DataFrame(st.session_state.results)
    st.dataframe(df, use_container_width=True)
    
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download Previous Results",
        data=csv,
        file_name="linkedin_contacts_previous.csv",
        mime="text/csv",
        key="download_previous"
    )

# Sidebar tips
st.sidebar.markdown("---")
st.sidebar.header("💡 Playwright Advantages")
st.sidebar.markdown("""
- **Better stealth**: Advanced anti-detection
- **Faster**: No ChromeDriver overhead  
- **More reliable**: Better JS handling
- **Multi-browser**: Chromium, Firefox, WebKit
- **Auto-wait**: Smart element waiting
- **Network control**: Block images/resources
""")

st.sidebar.markdown("---")
st.sidebar.header("⚡ Performance Tips")
st.sidebar.markdown("""
- **Block images**: Faster page loads
- **Increase delays**: Avoid rate limits
- **Use Firefox**: Sometimes less detected
- **Stealth mode**: Hide automation signals
- **Small batches**: Start with 1-2 pages
""")

# Installation instructions
with st.sidebar.expander("📦 Installation"):
    st.code("""
pip install playwright nest-asyncio
playwright install
    """)

st.markdown("---")
st.caption("⚠️ **Disclaimer**: Use responsibly and respect LinkedIn's Terms of Service. For educational purposes only.")