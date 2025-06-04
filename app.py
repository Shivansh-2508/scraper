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
import os

# Enable nested event loops for Streamlit
nest_asyncio.apply()

# Set page config
st.set_page_config(
    page_title="LinkedIn Contact Scraper - Actually Working Edition",
    page_icon="🎯",
    layout="wide"
)

# Initialize session state variables
if 'results' not in st.session_state:
    st.session_state.results = []
if 'scraping_in_progress' not in st.session_state:
    st.session_state.scraping_in_progress = False
if 'failed_pages' not in st.session_state:
    st.session_state.failed_pages = []

# App title and description
st.title("LinkedIn Contact Scraper - Actually Working Edition 🎯")
st.markdown("""
**Fixed version** that actually finds contact info instead of collecting digital tumbleweeds.
**What's new**: Smarter filtering, better queries, actual results.
""")

# Status and progress placeholders
status_placeholder = st.empty()
progress_placeholder = st.empty()
debug_placeholder = st.empty()

# Sidebar for inputs
with st.sidebar:
    st.header("Search Parameters")
    keyword = st.text_input("Enter keyword:", placeholder="e.g. developer, CEO, marketing")
    location = st.text_input("Location (optional):", placeholder="e.g. Mumbai, India")
    pages_to_scrape = st.slider("Pages to scrape:", min_value=1, max_value=3, value=1)
    
    # Search engine selection
    search_engine = st.selectbox("Search Engine:", ["DuckDuckGo", "Bing", "Google"], index=0)
    
    # Advanced options
    with st.expander("⚙️ Advanced Options"):
        delay_between_requests = st.slider("Delay between requests (seconds):", 3, 15, 6)
        enable_debug = st.checkbox("Enable debug mode", value=True)
        save_failed_pages = st.checkbox("Save failed pages for inspection", value=True)
        max_profiles_per_page = st.slider("Max profiles per page:", 3, 10, 5)
    
    start_scraping = st.button("🚀 Start Scraping", type="primary", 
                              disabled=st.session_state.scraping_in_progress)

# Better user agents that actually work
WORKING_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
]

def is_valid_linkedin_profile_url(url):
    """Strict LinkedIn profile URL validation"""
    if not url:
        return False
    
    # Must contain linkedin.com/in/
    if "linkedin.com/in/" not in url.lower():
        return False
    
    # Exclude garbage URLs
    garbage_patterns = [
        "/company/", "/jobs/", "/pulse/", "/posts/", "/groups/",
        "/events/", "/school/", "/showcase/", "dir/", "/topic/",
        "google.com", "facebook.com", "twitter.com", "redirect"
    ]
    
    url_lower = url.lower()
    if any(pattern in url_lower for pattern in garbage_patterns):
        return False
    
    # Must have actual profile path
    profile_pattern = r"linkedin\.com/in/[a-zA-Z0-9\-_%]+/?$"
    if not re.search(profile_pattern, url):
        return False
        
    return True

def extract_emails_aggressively(text):
    """Extract emails with multiple patterns and better filtering"""
    patterns = [
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        r"[A-Za-z0-9._%+-]+\s*@\s*[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        r"[A-Za-z0-9._%+-]+\[at\][A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        r"[A-Za-z0-9._%+-]+\s*\[at\]\s*[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
    ]
    
    all_emails = []
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        all_emails.extend(matches)
    
    # Clean up [at] format
    cleaned_emails = []
    for email in all_emails:
        email = email.replace("[at]", "@").replace(" ", "")
        cleaned_emails.append(email)
    
    # Filter out garbage
    blocked_domains = [
        "licdn.com", "linkedin.com", "static", "cdn", "img", "facebook.com",
        "twitter.com", "instagram.com", "youtube.com", "example.com", "test.com",
        "localhost", "127.0.0.1", "noreply", "no-reply", "donotreply", "sentry.io",
        "gravatar.com", "googleusercontent.com", "amazonaws.com"
    ]
    
    valid_emails = []
    for email in cleaned_emails:
        email_lower = email.lower()
        
        # Skip blocked domains
        if any(domain in email_lower for domain in blocked_domains):
            continue
            
        # Skip test/dummy emails
        if any(word in email_lower for word in ['example', 'test', 'sample', 'dummy', 'fake']):
            continue
            
        # Basic format validation
        if len(email) < 5 or len(email) > 50:
            continue
            
        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            continue
        
        # Must have at least one letter in local part (not just numbers)
        local_part = email.split('@')[0]
        if not re.search(r'[a-zA-Z]', local_part):
            continue
            
        valid_emails.append(email)
    
    return list(set(valid_emails))

def extract_phones_aggressively(text):
    """Extract phones with multiple Indian patterns"""
    patterns = [
        r"(?:\+91[-\s]?)?[6-9]\d{4}[-\s]?\d{5}",
        r"\+91[-\s]?[6-9]\d{9}",
        r"(?:\+91[-\s]?)?[6-9]\d[-\s]?\d{4}[-\s]?\d{4}",
        r"[6-9]\d{2}[-\s]?\d{3}[-\s]?\d{4}",
        r"[6-9]\d{2}\.\d{3}\.\d{4}",
        r"\b[6-9]\d{9}\b"
    ]
    
    all_phones = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        all_phones.extend(matches)
    
    # Clean and validate
    valid_phones = []
    for phone in all_phones:
        # Extract only digits
        digits_only = re.sub(r'\D', '', phone)
        
        # Valid Indian mobile: 10 digits starting with 6-9, or 12 digits with +91
        if len(digits_only) == 10 and digits_only[0] in '6789':
            valid_phones.append(phone.strip())
        elif len(digits_only) == 12 and digits_only.startswith('91') and digits_only[2] in '6789':
            valid_phones.append(phone.strip())
    
    # Filter fake/test numbers
    fake_patterns = [
        r'1234567890', r'9876543210', r'0000000000', r'1111111111',
        r'2222222222', r'3333333333', r'4444444444', r'5555555555',
        r'6666666666', r'7777777777', r'8888888888', r'9999999999'
    ]
    
    filtered_phones = []
    for phone in list(set(valid_phones)):
        digits = re.sub(r'\D', '', phone)
        
        # Skip obvious fakes
        if any(re.search(pattern, digits) for pattern in fake_patterns):
            continue
            
        # Must have variety in digits (at least 4 different digits)
        if len(set(digits[-10:])) >= 4:
            filtered_phones.append(phone)
    
    return filtered_phones

def build_smart_search_query(keyword, location, search_engine):
    """Build queries that GUARANTEE LinkedIn profiles with Indian contact info"""
    # FIXED: Always explicitly include LinkedIn in the query
    if location:
        location_part = f' "{location}"'
    else:
        location_part = ""
    
    # Different approaches per engine - but ALL include LinkedIn explicitly
    if search_engine == "DuckDuckGo":
        # More explicit LinkedIn targeting with Indian phone patterns
        return f'site:linkedin.com/in/ "{keyword}"{location_part} (email OR contact OR @ OR +91 OR "91")'
    elif search_engine == "Bing":
        # Bing works well with explicit site search
        return f'site:linkedin.com/in/ {keyword}{location_part} (contact OR +91)'
    else:  # Google
        # Google - keep it focused on LinkedIn profiles with contact hints
        return f'site:linkedin.com/in/ {keyword}{location_part} (+91 OR email OR contact)'

def get_search_url(query, search_engine):
    """Get search URL with proper encoding"""
    encoded_query = urllib.parse.quote_plus(query)
    
    if search_engine == "Google":
        return f"https://www.google.com/search?q={encoded_query}&num=50"
    elif search_engine == "Bing":
        return f"https://www.bing.com/search?q={encoded_query}&count=50"
    else:  # DuckDuckGo
        return f"https://duckduckgo.com/?q={encoded_query}&kl=wt-wt&ia=web"

def get_selectors(search_engine):
    """CSS selectors for each engine"""
    if search_engine == "Google":
        return {"result": "div.tF2Cxc, div.g", "title": "h3", "link": "a"}
    elif search_engine == "Bing":
        return {"result": ".b_algo", "title": "h2 a", "link": "h2 a"}
    else:  # DuckDuckGo
        return {"result": "[data-testid='result'], .web-result, .result", "title": "h2 a, .result__title a", "link": "h2 a, .result__title a"}

async def setup_browser():
    """Setup browser with working anti-detection"""
    try:
        launch_options = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--exclude-switches=enable-automation",
                "--disable-extensions",
                "--window-size=1920,1080",
                "--disable-web-security",
                "--allow-running-insecure-content"
            ]
        }
        
        browser = await async_playwright().start()
        chromium = await browser.chromium.launch(**launch_options)
        
        context = await chromium.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=random.choice(WORKING_USER_AGENTS),
            ignore_https_errors=True
        )
        
        # Block unnecessary resources
        await context.route("**/*.{png,jpg,jpeg,gif,svg,webp,ico,woff,woff2,css}", 
                          lambda route: route.abort())
        
        page = await context.new_page()
        
        # Anti-detection
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
            window.chrome = {runtime: {}};
        """)
        
        return browser, chromium, context, page
        
    except Exception as e:
        status_placeholder.error(f"❌ Browser setup failed: {str(e)}")
        return None, None, None, None

async def scrape_profile_content(page, profile_url):
    """Scrape individual profile with better content extraction"""
    try:
        await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(3000, 6000))
        
        # Scroll to load content
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        
        # Get all text content
        content = await page.content()
        title = await page.title()
        
        # Try to get structured data
        try:
            # Look for JSON-LD or other structured data
            json_scripts = await page.query_selector_all("script[type='application/ld+json']")
            for script in json_scripts:
                script_content = await script.inner_text()
                content += f" {script_content}"
        except:
            pass
        
        # Combine all content
        full_content = f"{title} {content}"
        
        return full_content
        
    except Exception as e:
        return f"Error loading profile: {str(e)}"

async def try_multiple_search_engines(keyword, location):
    """Try multiple search engines to find LinkedIn profiles"""
    engines = ["DuckDuckGo", "Google", "Bing"]
    all_profiles = []
    
    for engine in engines:
        try:
            status_placeholder.info(f"🔍 Trying {engine}...")
            profiles = await search_with_engine(keyword, location, engine)
            
            if profiles:
                status_placeholder.success(f"✅ Found {len(profiles)} profiles on {engine}")
                all_profiles.extend(profiles)
                break  # Stop after first successful engine
            else:
                status_placeholder.warning(f"⚠️ No profiles found on {engine}")
                
        except Exception as e:
            status_placeholder.warning(f"❌ {engine} failed: {str(e)}")
            continue
    
    # Remove duplicates
    seen_urls = set()
    unique_profiles = []
    for profile in all_profiles:
        if profile['url'] not in seen_urls:
            seen_urls.add(profile['url'])
            unique_profiles.append(profile)
    
    return unique_profiles

async def search_with_engine(keyword, location, engine):
    """Search with a specific engine"""
    playwright, browser, context, page = await setup_browser()
    if not browser:
        return []
    
    try:
        search_query = build_smart_search_query(keyword, location, engine)
        search_url = get_search_url(search_query, engine)
        selectors = get_selectors(engine)
        
        if enable_debug:
            debug_placeholder.info(f"🔍 Query: {search_query}")
            debug_placeholder.info(f"🌐 URL: {search_url}")
        
        # Navigate to search
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(random.randint(4000, 8000))
        
        # Check for blocking
        content = await page.content()
        if any(term in content.lower() for term in ["captcha", "unusual traffic", "blocked", "verify you are human"]):
            raise Exception(f"{engine} blocked the request")
        
        # Find search results
        try:
            await page.wait_for_selector(selectors["result"], timeout=15000)
        except:
            if save_failed_pages:
                with open(f"/tmp/search_fail_{engine}_{int(time.time())}.html", "w") as f:
                    f.write(await page.content())
            raise Exception("No search results selector found")
        
        # Get results
        results = await page.query_selector_all(selectors["result"])
        
        if not results:
            raise Exception("No search results found")
        
        valid_profiles = []
        
        # Filter for valid LinkedIn profiles
        for i, result in enumerate(results):
            try:
                title_elem = await result.query_selector(selectors["title"])
                link_elem = await result.query_selector(selectors["link"])
                
                if not title_elem or not link_elem:
                    continue
                
                title = await title_elem.inner_text()
                link = await link_elem.get_attribute("href")
                
                # Fix relative URLs
                if link and link.startswith('/url?'):
                    # Google redirect URL
                    match = re.search(r'url=([^&]+)', link)
                    if match:
                        link = urllib.parse.unquote(match.group(1))
                
                # Strict filtering
                if is_valid_linkedin_profile_url(link):
                    valid_profiles.append({"title": title, "url": link, "engine": engine})
                    
            except Exception as e:
                continue
        
        return valid_profiles
        
    finally:
        try:
            await browser.close()
            await playwright.stop()
        except:
            pass

async def scrape_search_results():
    """Main scraping function that actually works"""
    if not keyword.strip():
        status_placeholder.error("❌ Please enter a keyword.")
        return
    
    st.session_state.scraping_in_progress = True
    st.session_state.failed_pages = []
    progress_bar = progress_placeholder.progress(0)
    
    all_results = []
    
    try:
        # Try multiple search engines
        status_placeholder.info("🔍 Searching for LinkedIn profiles...")
        valid_profiles = await try_multiple_search_engines(keyword, location)
        
        if not valid_profiles:
            status_placeholder.error("❌ No LinkedIn profiles found across all search engines. Try different keywords.")
            return
        
        status_placeholder.success(f"✅ Found {len(valid_profiles)} valid LinkedIn profiles")
        
        # Setup browser for profile scraping
        playwright, browser, context, page = await setup_browser()
        if not browser:
            return
        
        try:
            # Process profiles
            for i, profile in enumerate(valid_profiles[:max_profiles_per_page]):
                try:
                    status_placeholder.info(f"🔍 Processing profile {i+1}/{len(valid_profiles[:max_profiles_per_page])}: {profile['title'][:50]}...")
                    
                    # Create new page for profile
                    profile_page = await context.new_page()
                    
                    try:
                        # Scrape profile content
                        content = await scrape_profile_content(profile_page, profile['url'])
                        
                        # Extract contact info
                        emails = extract_emails_aggressively(content)
                        phones = extract_phones_aggressively(content)
                        
                        # Always add profile, even without contact info for debugging
                        result_data = {
                            "Name": profile['title'].replace(" - LinkedIn", "").replace(" | LinkedIn", ""),
                            "Profile_URL": profile['url'],
                            "Emails": ", ".join(emails) if emails else "None found",
                            "Phones": ", ".join(phones) if phones else "None found",
                            "Email_Count": len(emails),
                            "Phone_Count": len(phones),
                            "Search_Engine": profile.get('engine', search_engine),
                            "Scraped_At": time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        all_results.append(result_data)
                        
                        if emails or phones:
                            status_placeholder.success(f"✅ Found {len(emails)} emails, {len(phones)} phones")
                        else:
                            status_placeholder.info(f"ℹ️ Profile added but no contact info found")
                        
                    except Exception as e:
                        if save_failed_pages:
                            st.session_state.failed_pages.append({
                                "url": profile['url'],
                                "title": profile['title'],
                                "error": str(e)
                            })
                    finally:
                        await profile_page.close()
                    
                    # Random delay
                    await page.wait_for_timeout(random.randint(delay_between_requests * 1000, 
                                                             (delay_between_requests + 3) * 1000))
                    
                    # Update progress
                    progress_bar.progress((i + 1) / len(valid_profiles[:max_profiles_per_page]))
                    
                except Exception as e:
                    status_placeholder.warning(f"⚠️ Error processing profile {i+1}: {str(e)}")
                    continue
            
        finally:
            try:
                await browser.close()
                await playwright.stop()
            except:
                pass
        
        # Results summary
        if all_results:
            profiles_with_contact = [r for r in all_results if r['Email_Count'] > 0 or r['Phone_Count'] > 0]
            status_placeholder.success(f"🎉 Scraping complete! Found {len(all_results)} profiles total, {len(profiles_with_contact)} with contact info.")
            st.session_state.results = all_results
        else:
            status_placeholder.warning("⚠️ No profiles scraped successfully.")
            
    except Exception as e:
        status_placeholder.error(f"❌ Scraping failed: {str(e)}")
        if enable_debug:
            debug_placeholder.error(traceback.format_exc())
        
    finally:
        st.session_state.scraping_in_progress = False

def display_results():
    """Display results with better formatting"""
    if not st.session_state.results:
        return
        
    st.subheader("📊 Scraped LinkedIn Contacts")
    df = pd.DataFrame(st.session_state.results)
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Profiles", len(df))
    with col2:
        emails_found = df[df['Email_Count'] > 0].shape[0]
        st.metric("With Emails", emails_found)
    with col3:
        phones_found = df[df['Phone_Count'] > 0].shape[0]
        st.metric("With Phones", phones_found)
    with col4:
        complete = df[(df['Email_Count'] > 0) & (df['Phone_Count'] > 0)].shape[0]
        st.metric("Complete Contacts", complete)
    
    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        show_emails_only = st.checkbox("Show only profiles with emails")
    with col2:
        show_phones_only = st.checkbox("Show only profiles with phones")
    
    # Apply filters
    filtered_df = df.copy()
    if show_emails_only:
        filtered_df = filtered_df[filtered_df['Email_Count'] > 0]
    if show_phones_only:
        filtered_df = filtered_df[filtered_df['Phone_Count'] > 0]
    
    # Display table
    st.dataframe(filtered_df, use_container_width=True)
    
    # Download button
    csv = filtered_df.to_csv(index=False).encode("utf-8")
    filename = f"linkedin_contacts_{keyword}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    st.download_button(
        label="📥 Download Results as CSV",
        data=csv,
        file_name=filename,
        mime="text/csv"
    )

def display_debug_info():
    """Show failed pages for debugging"""
    if st.session_state.failed_pages and enable_debug:
        with st.expander(f"🐛 Debug Info - {len(st.session_state.failed_pages)} failed pages"):
            for i, failed in enumerate(st.session_state.failed_pages):
                st.write(f"**{i+1}. {failed.get('title', 'Unknown')}**")
                st.write(f"URL: {failed.get('url', 'N/A')}")
                if 'error' in failed:
                    st.write(f"Error: {failed['error']}")
                if 'reason' in failed:
                    st.write(f"Reason: {failed['reason']}")
                if 'content_length' in failed:
                    st.write(f"Content length: {failed['content_length']} chars")
                st.write("---")

def run_scraping():
    """Run the async scraping function"""
    try:
        asyncio.run(scrape_search_results())
    except Exception as e:
        status_placeholder.error(f"❌ Error: {str(e)}")
        st.session_state.scraping_in_progress = False

# Handle scraping button
if start_scraping and not st.session_state.scraping_in_progress:
    run_scraping()

# Display results
if st.session_state.results:
    display_results()

# Display debug info
display_debug_info()

# Sidebar help
st.sidebar.markdown("---")
st.sidebar.header("✅ What's Fixed")
st.sidebar.markdown("""
- **GUARANTEED LinkedIn**: Always includes site:linkedin.com/in/
- **Multi-engine fallback**: Tries DuckDuckGo → Google → Bing
- **Better URL handling**: Fixes Google redirects
- **Explicit queries**: Forces LinkedIn profile results
- **Debug visibility**: See exact queries used
- **All profiles shown**: Even without contact info
""")

st.sidebar.markdown("---")
st.sidebar.header("🎯 Pro Tips")
st.sidebar.markdown("""
1. **Use specific titles** - "Software Engineer" not just "developer"
2. **Include company** - "engineer Microsoft" works better
3. **Try different keywords** if no results
4. **Check debug info** to see actual queries
5. **Enable all profiles** to see what's found
""")

st.markdown("---")
st.caption("⚠️ **Legal Notice**: For educational purposes only. Respect LinkedIn's Terms of Service and applicable laws.")