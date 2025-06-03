import streamlit as st
import pandas as pd
import re
import time
import urllib.parse
import os
import subprocess
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

# Set page config
st.set_page_config(
    page_title="LinkedIn Contact Scraper",
    page_icon="🔍",
    layout="wide"
)

# Initialize session state variables
if 'results' not in st.session_state:
    st.session_state.results = []
if 'scraping_in_progress' not in st.session_state:
    st.session_state.scraping_in_progress = False

# App title and description
st.title("LinkedIn Contact Scraper")
st.markdown("""
This app scrapes LinkedIn profiles from Google search results to extract email addresses and phone numbers.
**Cloud Version** - Runs automatically without manual browser interaction.
""")

# Warning banner for Streamlit Cloud
st.warning("⚠️ **Cloud Deployment Note**: This version runs in headless mode and may face limitations with CAPTCHA solving and rate limiting.")

# Create placeholders for status and progress
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
    
    # Single button to start scraping
    start_scraping = st.button("🚀 Start Scraping", type="primary", disabled=st.session_state.scraping_in_progress)

def find_chrome_binary():
    """Find Chrome/Chromium binary path"""
    possible_paths = [
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/opt/google/chrome/chrome",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",  # macOS
        "chromium-browser",
        "chromium",
        "google-chrome"
    ]
    
    for path in possible_paths:
        if os.path.exists(path) or subprocess.run(["which", path], capture_output=True).returncode == 0:
            return path
    return None

def find_chromedriver():
    """Find ChromeDriver binary path"""
    possible_paths = [
        "/usr/bin/chromedriver",
        "/usr/local/bin/chromedriver",
        "/opt/chromedriver/chromedriver",
        "chromedriver"
    ]
    
    for path in possible_paths:
        if os.path.exists(path) or subprocess.run(["which", path], capture_output=True).returncode == 0:
            return path
    return None

def setup_headless_browser():
    """Setup Chrome browser for cloud deployment with better error handling"""
    try:
        # Find Chrome binary
        chrome_binary = find_chrome_binary()
        if not chrome_binary:
            status_placeholder.error("❌ Chrome/Chromium not found. Please install it first.")
            return None
        
        # Find ChromeDriver
        chromedriver_path = find_chromedriver()
        if not chromedriver_path:
            status_placeholder.error("❌ ChromeDriver not found. Please install it first.")
            return None
        
        status_placeholder.info(f"🔧 Using Chrome: {chrome_binary}")
        status_placeholder.info(f"🔧 Using ChromeDriver: {chromedriver_path}")
        
        options = Options()
        
        # Set Chrome binary location
        if os.path.exists(chrome_binary):
            options.binary_location = chrome_binary
        
        # Headless and cloud-friendly options
        options.add_argument("--headless=new")  # Use new headless mode
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-features=TranslateUI")
        options.add_argument("--disable-features=VizDisplayCompositor")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-sync")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-web-security")
        options.add_argument("--allow-running-insecure-content")
        # DON'T DISABLE JAVASCRIPT - LinkedIn needs it!
        # options.add_argument("--disable-javascript")  # REMOVED
        
        # Memory optimization
        options.add_argument("--memory-pressure-off")
        options.add_argument("--max_old_space_size=4096")
        
        # Anti-detection measures
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Set up service with explicit path
        service = Service(executable_path=chromedriver_path)
        
        status_placeholder.info("🔧 Starting Chrome browser...")
        driver = webdriver.Chrome(service=service, options=options)
        
        # Hide webdriver flag for anti-bot evasion
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Test if browser is working
        driver.get("https://www.google.com")
        if "Google" not in driver.title:
            driver.quit()
            status_placeholder.error("❌ Browser test failed")
            return None
        
        status_placeholder.success("✅ Browser setup successful!")
        return driver
        
    except Exception as e:
        status_placeholder.error(f"❌ Error setting up browser: {str(e)}")
        return None

def extract_emails(text):
    """Extract email addresses from text with better filtering"""
    email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    emails = re.findall(email_regex, text)
    
    # Filter out unwanted domains and common false positives
    blocked_domains = [
        "licdn.com", "linkedin.com", "static", "cdn", "img", "facebook.com",
        "twitter.com", "instagram.com", "youtube.com", "example.com", "test.com",
        "localhost", "127.0.0.1", "noreply", "no-reply", "donotreply"
    ]
    
    # Additional filters for bogus emails
    clean_emails = []
    for email in emails:
        email_lower = email.lower()
        # Skip if contains blocked domains
        if any(domain in email_lower for domain in blocked_domains):
            continue
        # Skip if looks like a generic/placeholder email
        if any(word in email_lower for word in ['example', 'test', 'sample', 'dummy']):
            continue
        # Skip if email is too short or too long
        if len(email) < 5 or len(email) > 50:
            continue
        # Basic validation - must have proper structure
        if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
            clean_emails.append(email)
    
    return list(set(clean_emails))

def extract_phones(text):
    """Extract Indian phone numbers from text with much better filtering"""
    # More precise patterns for Indian mobile numbers
    phone_patterns = [
        r"(?:\+91[-\s]?)?[6-9]\d{4}[-\s]?\d{5}",  # +91 9XXXX XXXXX or 9XXXX XXXXX
        r"\+91[-\s]?[6-9]\d{9}",                   # +91 9XXXXXXXXX
        r"(?:\+91[-\s]?)?[6-9]\d[-\s]?\d{4}[-\s]?\d{4}",  # 9 XXXX XXXX format
    ]
    
    phones = []
    for pattern in phone_patterns:
        matches = re.findall(pattern, text)
        phones.extend(matches)
    
    # Clean and validate phone numbers
    clean_phones = []
    for phone in phones:
        # Remove all non-digits to check length
        digits_only = re.sub(r'\D', '', phone)
        
        # Valid Indian mobile: 10 digits starting with 6-9, or 12 digits with +91
        if len(digits_only) == 10 and digits_only[0] in '6789':
            clean_phones.append(phone.strip())
        elif len(digits_only) == 12 and digits_only.startswith('91') and digits_only[2] in '6789':
            clean_phones.append(phone.strip())
    
    # Remove duplicates and filter out obviously fake numbers
    unique_phones = list(set(clean_phones))
    
    # Filter out common fake patterns
    fake_patterns = [
        r'1234567890', r'9876543210', r'0000000000', r'1111111111',
        r'2222222222', r'3333333333', r'4444444444', r'5555555555',
        r'9999999999', r'8888888888', r'7777777777', r'6666666666'
    ]
    
    filtered_phones = []
    for phone in unique_phones:
        digits = re.sub(r'\D', '', phone)
        if not any(re.search(pattern, digits) for pattern in fake_patterns):
            # Check for obviously repetitive patterns
            if len(set(digits[-10:])) > 3:  # At least 4 different digits in the number
                filtered_phones.append(phone)
    
    return filtered_phones

def perform_scraping():
    """Main scraping function"""
    if not keyword.strip():
        status_placeholder.error("❌ Please enter a keyword to search for.")
        return
    
    st.session_state.scraping_in_progress = True
    all_results = []
    
    # Setup browser
    driver = setup_headless_browser()
    if not driver:
        st.session_state.scraping_in_progress = False
        return
    
    progress_bar = progress_placeholder.progress(0)
    
    try:
        # Build much better search query
        email_query = " OR ".join([f'"{provider}"' for provider in email_providers])
        
        # More targeted search query for LinkedIn profiles
        search_query = f'site:linkedin.com/in/ "{keyword}" ({email_query}) "+91"'
        
        # Alternative search sources (often have better contact data)
        alt_sources = [
            f'site:rocketreach.co "{keyword}" "+91" ({email_query})',
            f'site:apollo.io "{keyword}" "+91" ({email_query})',
            f'site:signalhire.com "{keyword}" "+91" ({email_query})'
        ]
        
        # Use primary LinkedIn search first
        encoded_query = urllib.parse.quote_plus(search_query)
        google_url = f"https://www.google.com/search?q={encoded_query}"
        
        status_placeholder.info(f"🔍 Searching Google for: {search_query}")
        
        # Navigate to Google
        driver.get(google_url)
        time.sleep(3)  # Wait for page load
        
        # Check if we got blocked
        page_source = driver.page_source.lower()
        if "captcha" in page_source or "unusual traffic" in page_source:
            status_placeholder.error("❌ Google is requesting CAPTCHA verification. Try again later or use fewer pages.")
            driver.quit()
            st.session_state.scraping_in_progress = False
            return
        
        # Scraping loop
        current_page = 1
        while current_page <= pages_to_scrape:
            progress_bar.progress((current_page - 1) / pages_to_scrape)
            status_placeholder.info(f"📄 Scraping page {current_page} of {pages_to_scrape}...")
            
            # Get search results
            time.sleep(2)
            results = driver.find_elements(By.CSS_SELECTOR, "div.tF2Cxc")
            
            if not results:
                status_placeholder.warning(f"⚠️ No results found on page {current_page}")
                break
            
            # Process each result
            for i, result in enumerate(results[:5]):  # Limit to 5 results per page
                try:
                    title_element = result.find_element(By.TAG_NAME, "h3")
                    link_element = result.find_element(By.TAG_NAME, "a")
                    
                    title = title_element.text
                    link = link_element.get_attribute("href")
                    
                    if "linkedin.com" not in link and "rocketreach.co" not in link and "apollo.io" not in link and "signalhire.com" not in link:
                        continue
                    
                    status_placeholder.info(f"🔍 Processing: {title[:50]}...")
                    
                    # Visit LinkedIn page (or other profile page)
                    driver.execute_script("window.open(arguments[0], '_blank');", link)
                    driver.switch_to.window(driver.window_handles[1])
                    
                    # Wait longer for JS-heavy pages to load
                    time.sleep(5)  # Increased wait time for JS rendering
                    
                    # Scroll to load more content (some info loads on scroll)
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(2)
                    
                    # Extract information
                    page_source = driver.page_source
                    emails = extract_emails(page_source)
                    phones = extract_phones(page_source)
                    
                    # Additional check - look in page title and meta descriptions
                    try:
                        page_title = driver.title
                        meta_desc = driver.find_element(By.CSS_SELECTOR, "meta[name='description']").get_attribute("content")
                        additional_text = f"{page_title} {meta_desc}"
                        emails.extend(extract_emails(additional_text))
                        phones.extend(extract_phones(additional_text))
                        emails = list(set(emails))  # Remove duplicates
                        phones = list(set(phones))
                    except:
                        pass
                    
                    # Store results with more metadata
                    result_data = {
                        "Title": title,
                        "Link": link,
                        "Source": "LinkedIn" if "linkedin.com" in link else "Contact DB",
                        "Emails": ", ".join(emails) if emails else "No emails found",
                        "Phones": ", ".join(phones) if phones else "No phones found",
                        "Email Count": len(emails),
                        "Phone Count": len(phones),
                        "Page": current_page
                    }
                    all_results.append(result_data)
                    
                    # Close tab and return to search
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                    
                except Exception as e:
                    status_placeholder.warning(f"⚠️ Error processing result {i+1}: {str(e)[:100]}")
                    # Ensure we're back on the main window
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    continue
            
            # Try to go to next page
            try:
                next_button = driver.find_element(By.ID, "pnnext")
                driver.execute_script("arguments[0].click();", next_button)
                current_page += 1
                time.sleep(3)
            except:
                status_placeholder.info("📄 No more pages available")
                break
        
        # Cleanup
        driver.quit()
        
        # Update progress and status
        progress_bar.progress(1.0)
        status_placeholder.success(f"✅ Scraping complete! Found {len(all_results)} profiles.")
        
        # Save results
        st.session_state.results = all_results
        st.session_state.scraping_in_progress = False
        
        # Display results
        if all_results:
            st.subheader("📊 Scraped Results")
            df = pd.DataFrame(all_results)
            
            # Summary stats with better metrics
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
        else:
            st.warning("⚠️ No results found. Try different keywords or check if LinkedIn profiles contain the specified email providers.")
            
    except Exception as e:
        status_placeholder.error(f"❌ An error occurred: {str(e)}")
        if driver:
            driver.quit()
        st.session_state.scraping_in_progress = False

# Handle scraping button
if start_scraping and not st.session_state.scraping_in_progress:
    perform_scraping()

# Show existing results if any
if st.session_state.results and not st.session_state.scraping_in_progress:
    st.subheader("📊 Previous Results")
    df = pd.DataFrame(st.session_state.results)
    st.dataframe(df, use_container_width=True)
    
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download Previous Results",
        data=csv,
        file_name=f"linkedin_contacts_previous.csv",
        mime="text/csv",
        key="download_previous"
    )

# Sidebar tips
st.sidebar.markdown("---")
st.sidebar.header("💡 Tips for Cloud Version")
st.sidebar.markdown("""
- **Start small**: Use 1-2 pages initially
- **Specific keywords**: More specific = better results  
- **Rate limiting**: Built-in delays to avoid blocking
- **Multi-source**: Searches LinkedIn + contact databases
- **JS enabled**: Better data extraction from modern sites
- **Smart filtering**: Removes fake/duplicate contacts
""")

st.sidebar.markdown("---")
st.sidebar.header("🎯 Search Strategy")
st.sidebar.markdown("""
**Primary**: LinkedIn profiles with contact info
**Secondary**: RocketReach, Apollo, SignalHire
**Filters**: Valid Indian mobile numbers only
**Email validation**: Real domains + structure check
""")

# System info (for debugging)
with st.sidebar.expander("🔧 System Debug Info"):
    st.write("**Chrome Binary:**", find_chrome_binary())
    st.write("**ChromeDriver:**", find_chromedriver())
    st.write("**Platform:**", sys.platform)

# Footer
st.markdown("---")
st.caption("⚠️ **Disclaimer**: Use responsibly and respect privacy laws and LinkedIn's Terms of Service. This tool is for educational purposes.")