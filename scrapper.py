import streamlit as st
import pandas as pd
import re
import time
import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

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

def setup_headless_browser():
    """Setup Chrome browser for cloud deployment"""
    options = Options()
    
    # Classic headless mode for maximum compatibility
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-features=VizDisplayCompositor")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")  # Optional: speeds up loads, but might break some layouts
    # **REMOVED** options.add_argument("--disable-javascript")  # DO NOT disable JS or LinkedIn breaks

    options.binary_location = "/usr/bin/chromium-browser"

    # Anti-detection measures
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        status_placeholder.info("🔧 Setting up headless browser...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # Hide webdriver flag for anti-bot evasion
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    except Exception as e:
        status_placeholder.error(f"❌ Error setting up browser: {e}")
        return None

def extract_emails(text):
    """Extract email addresses from text"""
    email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    emails = re.findall(email_regex, text)
    
    # Filter out unwanted domains
    blocked_domains = ["licdn.com", "linkedin.com", "static", "cdn", "img"]
    clean_emails = [email for email in emails 
                   if not any(domain in email.lower() for domain in blocked_domains)]
    
    return list(set(clean_emails))

def extract_phones(text):
    """Extract Indian phone numbers from text"""
    phone_patterns = [
        r"\+91[-\s]?\d{5}[-\s]?\d{5}",  # +91 12345 67890
        r"\+91\d{10}",                   # +9112345678901
        r"\+91[-\s]?\d{4}[-\s]?\d{3}[-\s]?\d{3}",  # +91 1234 567 890
        r"91[-\s]?\d{10}",               # 91 1234567890
        r"\d{5}[-\s]?\d{5}"              # 12345 67890
    ]
    
    phones = []
    for pattern in phone_patterns:
        phones.extend(re.findall(pattern, text))
    
    return list(set(phones))

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
        # Build search query
        email_query = " OR ".join([f'"{provider}"' for provider in email_providers])
        search_query = f'"+91" & {keyword} ({email_query}) site:linkedin.com'
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
                    
                    if "linkedin.com" not in link:
                        continue
                    
                    status_placeholder.info(f"🔍 Processing: {title[:50]}...")
                    
                    # Visit LinkedIn page
                    driver.execute_script("window.open(arguments[0], '_blank');", link)
                    driver.switch_to.window(driver.window_handles[1])
                    
                    time.sleep(3)  # Wait for page load
                    
                    # Extract information
                    page_source = driver.page_source
                    emails = extract_emails(page_source)
                    phones = extract_phones(page_source)
                    
                    # Store results
                    all_results.append({
                        "Title": title,
                        "Link": link,
                        "Emails": ", ".join(emails) if emails else "No emails found",
                        "Phones": ", ".join(phones) if phones else "No phones found",
                        "Page": current_page
                    })
                    
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
            
            # Summary stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Profiles", len(df))
            with col2:
                emails_found = df[df['Emails'] != 'No emails found'].shape[0]
                st.metric("Profiles with Emails", emails_found)
            with col3:
                phones_found = df[df['Phones'] != 'No phones found'].shape[0]
                st.metric("Profiles with Phones", phones_found)
            
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
- **No CAPTCHA solving**: If blocked, try again later
- **Headless mode**: Runs without browser window
""")

# Footer
st.markdown("---")
st.caption("⚠️ **Disclaimer**: Use responsibly and respect privacy laws and LinkedIn's Terms of Service. This tool is for educational purposes.")