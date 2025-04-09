from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import re
import pandas as pd
import urllib.parse

# User Inputs
keyword = input("Enter keyword to refine search (or press Enter to skip): ")
pages_to_scrape = int(input("Enter number of pages to scrape: "))

# Email Providers
email_providers = ["@gmail.com", "@yahoo.com", "@outlook.com", "@rediffmail.com"]
email_query = " OR ".join([f'"{provider}"' for provider in email_providers])

# Google Search Query (Properly Encoded)
SEARCH_QUERY = f'"+91" {keyword} ({email_query}) site:linkedin.com'
ENCODED_QUERY = urllib.parse.quote_plus(SEARCH_QUERY)
GOOGLE_URL = f"https://www.google.com/search?q={ENCODED_QUERY}"

# Setup Chrome
options = Options()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

# Initialize WebDriver
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

def scrape_google_results(pages):
    all_results = []
    driver.get(GOOGLE_URL)
    input("⚠️ Solve CAPTCHA (if any), then press Enter to continue...")  # Manual CAPTCHA solving
    
    for page in range(pages):
        time.sleep(5)  # Allow page to load
        results = driver.find_elements(By.CSS_SELECTOR, "div.tF2Cxc")
        
        for result in results:
            try:
                title = result.find_element(By.TAG_NAME, "h3").text
                link = result.find_element(By.TAG_NAME, "a").get_attribute("href")

                # Visit LinkedIn page
                driver.execute_script("window.open(arguments[0], '_blank');", link)
                driver.switch_to.window(driver.window_handles[1])
                time.sleep(5)
                
                page_source = driver.execute_script("return document.body.innerHTML")
                emails = extract_emails(page_source)
                phones = extract_phones(page_source)
                
                all_results.append({
                    "Title": title,
                    "Link": link,
                    "Emails": ", ".join(emails) if emails else "N/A",
                    "Phones": ", ".join(phones) if phones else "N/A",
                })
                
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
            except Exception as e:
                print(f"Error: {e}")
        
        try:
            next_button = driver.find_element(By.LINK_TEXT, "Next")
            next_button.click()
        except:
            print("⚠️ No more pages available.")
            break
    
    return all_results

# Regex Functions (Improved Email Extraction)
def extract_emails(text):
    # Extract properly formatted emails
    email_regex = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    emails = re.findall(email_regex, text)

    # Handle obfuscated emails (e.g., abc [at] gmail [dot] com)
    obfuscated_regex = r"([a-zA-Z0-9._%+-]+)\s*\[at\]\s*([a-zA-Z0-9.-]+)\s*\[dot\]\s*([a-zA-Z]{2,})"
    obfuscated_emails = re.findall(obfuscated_regex, text)
    for user, domain, tld in obfuscated_emails:
        emails.append(f"{user}@{domain}.{tld}")

    return list(set(emails))

def extract_phones(text):
    return list(set(re.findall(r"\+91[-\s]?\d{5}[-\s]?\d{5}", text)))

# Save to CSV
def save_to_csv(results):
    if results:
        df = pd.DataFrame(results)
        df.to_csv("linkedin_contacts.csv", index=False)
        print("✅ Data saved to linkedin_contacts.csv")
    else:
        print("⚠️ No contacts found!")

if __name__ == "__main__":
    results = scrape_google_results(pages_to_scrape)
    save_to_csv(results)
    driver.quit()
    print("✅ Scraping complete!")

