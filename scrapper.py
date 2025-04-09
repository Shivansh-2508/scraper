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

# Initialize session state variables if they don't exist
if 'driver' not in st.session_state:
    st.session_state.driver = None
if 'results' not in st.session_state:
    st.session_state.results = []
if 'scraping_in_progress' not in st.session_state:
    st.session_state.scraping_in_progress = False
if 'browser_started' not in st.session_state:
    st.session_state.browser_started = False
if 'captcha_solved' not in st.session_state:
    st.session_state.captcha_solved = False
if 'results_displayed' not in st.session_state:
    st.session_state.results_displayed = False

# App title and description
st.title("LinkedIn Contact Scraper")
st.markdown("""
This app scrapes LinkedIn profiles from Google search results to extract email addresses and phone numbers.
Please use responsibly and in accordance with all applicable laws and terms of service.
""")

# Create placeholders for status and progress
status_placeholder = st.empty()
progress_placeholder = st.empty()

# Sidebar for inputs
with st.sidebar:
    st.header("Search Parameters")
    keyword = st.text_input("Enter keyword to refine search:", placeholder="e.g. developer, CEO, marketing")
    pages_to_scrape = st.slider("Number of pages to scrape:", min_value=1, max_value=10, value=3)
    email_providers = st.multiselect(
        "Email providers to search for:",
        ["@gmail.com", "@yahoo.com", "@outlook.com", "@rediffmail.com", "@hotmail.com"],
        default=["@gmail.com", "@yahoo.com", "@outlook.com", "@rediffmail.com"]
    )
    
    # Buttons for different stages of the process
    col1, col2 = st.columns(2)
    
    with col1:
        if not st.session_state.browser_started:
            start_browser = st.button("Start Browser", type="primary")
        else:
            start_scraping = st.button("Start Scraping", type="primary")
    
    with col2:
        if st.session_state.browser_started:
            close_browser = st.button("Close Browser", type="secondary")

# Functions for scraping



def extract_emails(text):
    # Strict email regex
    email_regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    emails = re.findall(email_regex, text)

    # Remove LinkedIn system emails (like static.licdn.com)
    blocked_domains = ["licdn.com", "linkedin.com", "please", "videos", "information"]
    clean_emails = [email for email in emails if not any(domain in email for domain in blocked_domains)]

    return list(set(clean_emails))  # Remove duplicates
def extract_phones(text):
    # Improved regex to match multiple formats
    phone_regex = r"\+91[-\s]?\d{5}[-\s]?\d{5}|\+91\d{10}|\+91[-\s]?\d{4}[-\s]?\d{3}[-\s]?\d{3}"
    return list(set(re.findall(phone_regex, text)))


def setup_and_open_browser():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # Critical: Keep browser open
    options.add_experimental_option("detach", True)
    
    status_placeholder.info("Starting Chrome browser...")
    
    try:
        # Create a new Chrome WebDriver
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        
        # Build search query
        email_query = " OR ".join([f'"{provider}"' for provider in email_providers])
        search_query = f'"+91" {keyword} ({email_query}) site:linkedin.com'
        encoded_query = urllib.parse.quote_plus(search_query)
        google_url = f"https://www.google.com/search?q={encoded_query}"
        
        # Navigate to Google
        driver.get(google_url)
        
        st.session_state.driver = driver
        st.session_state.browser_started = True
        status_placeholder.success("Browser opened successfully! Solve any CAPTCHA if needed, then click 'Start Scraping'")
        
        # Store parameters for later use
        st.session_state.keyword = keyword
        st.session_state.pages_to_scrape = pages_to_scrape
        st.session_state.email_providers = email_providers
        
        return driver
    except Exception as e:
        status_placeholder.error(f"Error launching browser: {e}")
        return None

def perform_scraping():
    if not st.session_state.driver:
        status_placeholder.error("Browser not initialized. Please start the browser first.")
        return
    
    driver = st.session_state.driver
    all_results = []
    st.session_state.scraping_in_progress = True
    
    progress_bar = progress_placeholder.progress(0)
    
    try:
        # Main scraping loop
        current_page = 1
        while current_page <= st.session_state.pages_to_scrape:
            progress_bar.progress((current_page - 1) / st.session_state.pages_to_scrape)
            status_placeholder.info(f"Scraping page {current_page} of {st.session_state.pages_to_scrape}...")
            
            # Get search results
            time.sleep(2)  # Wait for page to fully load
            results = driver.find_elements(By.CSS_SELECTOR, "div.tF2Cxc")
            
            if not results:
                status_placeholder.warning(f"No results found on page {current_page}. Moving to next page...")
            
            # Process each result
            for result in results:
                try:
                    title = result.find_element(By.TAG_NAME, "h3").text
                    link = result.find_element(By.TAG_NAME, "a").get_attribute("href")
                    
                    status_placeholder.info(f"Visiting: {title}")
                    
                    # Open LinkedIn page in new tab
                    original_window = driver.current_window_handle
                    driver.execute_script("window.open(arguments[0], '_blank');", link)
                    
                    # Switch to the new tab
                    driver.switch_to.window(driver.window_handles[1])
                    time.sleep(3)  # Wait for page to load
                    
                    # Extract information
                    page_source = driver.page_source
                    emails = extract_emails(page_source)
                    phones = extract_phones(page_source)
                    
                    # Store the results
                    all_results.append({
                        "Title": title,
                        "Link": link,
                        "Emails": ", ".join(emails) if emails else "N/A",
                        "Phones": ", ".join(phones) if phones else "N/A",
                    })
                    
                    # Close tab and go back to search results
                    driver.close()
                    driver.switch_to.window(original_window)
                    
                except Exception as e:
                    status_placeholder.error(f"Error processing result: {str(e)}")
                    # Make sure we return to the main window
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
            
            # Try to navigate to next page
            try:
                next_button = driver.find_element(By.LINK_TEXT, "Next")
                next_button.click()
                current_page += 1
                time.sleep(2)  # Wait for page transition
            except Exception as e:
                status_placeholder.warning("No more pages available or reached the end.")
                break
        
        # Update progress and status
        progress_bar.progress(1.0)
        status_placeholder.success("✅ Scraping complete!")
        
        # Save results and update app state
        st.session_state.results = all_results
        st.session_state.scraping_in_progress = False
        st.session_state.results_displayed = True
        
        # Display results table
        if all_results:
            st.subheader("Scraped Results")
            df = pd.DataFrame(all_results)
            st.dataframe(df)
            
            # Download button - with unique key
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download as CSV",
                data=csv,
                file_name="linkedin_contacts.csv",
                mime="text/csv",
                key="download_after_scraping"  # Added unique key
            )
        else:
            st.warning("No results found. Try adjusting your search parameters.")
            
    except Exception as e:
        status_placeholder.error(f"An error occurred during scraping: {str(e)}")
        st.session_state.scraping_in_progress = False

# Handle button actions
if 'start_browser' in locals() and start_browser:
    setup_and_open_browser()
    st.rerun()

if 'start_scraping' in locals() and start_scraping:
    perform_scraping()

if 'close_browser' in locals() and close_browser:
    if st.session_state.driver:
        try:
            st.session_state.driver.quit()
            status_placeholder.info("Browser closed successfully.")
        except:
            status_placeholder.warning("Browser may have already closed.")
    
    # Reset state
    st.session_state.driver = None
    st.session_state.browser_started = False
    st.session_state.scraping_in_progress = False
    st.session_state.results_displayed = False
    st.rerun()

# Show results if they exist, scraping is not in progress, and they haven't been displayed in the scraping function
if (not st.session_state.scraping_in_progress and 
    st.session_state.results and 
    not st.session_state.results_displayed):
    
    st.subheader("Scraped Results")
    df = pd.DataFrame(st.session_state.results)
    st.dataframe(df)
    
    # Download button - with different unique key
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download as CSV",
        data=csv,
        file_name="linkedin_contacts.csv",
        mime="text/csv",
        key="download_from_state"  # Added different unique key
    )

# Add helpful tips
st.sidebar.markdown("---")
st.sidebar.header("Tips")
st.sidebar.markdown("""
- Use specific keywords for better results
- If you see a CAPTCHA, solve it before clicking 'Start Scraping'
- The browser window must stay open during scraping
- Before closing the app, click 'Close Browser' to clean up
""")

# Footer
st.markdown("---")
st.caption("⚠️ Note: Please use this tool ethically and respect privacy and terms of service.")