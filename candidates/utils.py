import os
import google.generativeai as genai
from django.conf import settings
import random
import platform
import json
import time
import urllib.parse
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import psutil
import shutil
from .constants import *
from .models import Job, JobSearch, CVData, CreditAction, CV
from django.core.files.storage import default_storage
from paypalcheckoutsdk.core import PayPalHttpClient, SandboxEnvironment
from bs4 import BeautifulSoup
import re
import asyncio
import aiohttp
from datetime import datetime
import requests
from fake_useragent import UserAgent
from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from .serializers import CVDataSerializer
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from PIL import Image
from selenium.webdriver.chrome.service import Service
import chromedriver_autoinstaller
from django.core.files import File
import base64
import tempfile
from django.core.files.base import ContentFile
from io import BytesIO
from pdf2image import convert_from_bytes
import string


ua = UserAgent()
client_id = os.getenv('PAYPAL_CLIENT_ID')
client_secret = os.getenv('PAYPAL_CLIENT_SECRET')
environment = SandboxEnvironment(client_id=client_id, client_secret=client_secret)
paypal_client = PayPalHttpClient(environment)
MAX_TOTAL = 200
PRICE_TABLE = {
    20: 60,
    40: 120,
    60: 180,
    80: 240,
    100: 300,
    200: 398,
    400: 796,
    600: 1194,
    800: 1592,
    1000: 1990,
    2000: 1980,
    4000: 3960,
    6000: 5940,
    8000: 7920,
    10000: 9900
}
ALLOWED_JOB_DOMAINS = {
    "linkedin.com": "/jobs/view/",
    "indeed.com": "/rc/clk/"
}
Cookies = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Cookie": 'JSESSIONID=ajax:7848041967472204636; lang=v=2&lang=en-us; bcookie="v=2&e5d26d20-ae1c-42bb-8d62-eb5447692036"; bscookie="v=1&20241215044610fbdb271d-e8b0-412d-89f6-da4f56e3a923AQGQvJZV9wbqclWCiMLwhnGu5ZFY4OmJ"; lidc="b=VGST00:s=V:r=V:a=V:p=V:g=3516:u=1:x=1:i=1734237970:t=1734324370:v=2:sig=AQEqO6q4wUsqR1mj-IwI8yHEBSAQ8KP-"; AMCVS_14215E3D5995C57C0A495C55%40AdobeOrg=1; _gcl_au=1.1.1133647765.1734241347; __cf_bm=ZHOfMYL0.WenI3RhHWMQsQ_mtspTnVnI3k0PTMf5HXA-1734256120-1.0.1.1-JDhdDn5NmYf6DZLz_972zyLhHGer_6BJgNUascersqKO6_1XuYayFLI1KYFVHDDWWGCqZnrX2SN1sd19AyHedQ; _uetsid=5da19ed0baa711efb7f4279e395081d5; _uetvid=5da1d750baa711ef9b0747d65465cd51; AMCV_14215E3D5995C57C0A495C55%40AdobeOrg=-637568504%7CMCIDTS%7C20073%7CMCMID%7C42801921487020161892225787033943760464%7CMCAAMLH-1734861054%7C6%7CMCAAMB-1734861054%7C6G1ynYcLPuiQxYZrsz_pkqfLG9yMXBpb2zX5dvJdYQJzPXImdj0y%7CMCOPTOUT-1734263454s%7CNONE%7CvVersion%7C5.1.1; aam_uuid=42990763440476163742174318049666117019; ccookie=0001AQH75bAWf2cLlgAAAZPJvkBI3nO8UfPNWap+B1Bi5NyQywHD5P5/ReAUufFnzFUWNIWC29YroQeNi+adBDegEOWdxb2VLF9zRAt1eZhwAyzc1IzyRkMl7GYBFO5I4AG2n9qDMyByiVAWIqg5H5TKSFkhzQgq7w9tySbyKqftOyuiSmT3; fid=AQFycxUlXPfaYAAAAZPJvnY71ClLx10eBwDihj-kYLKFBS2_tFZVSGZcPi6E4zls6nboUn5ijEDBCg; fcookie=AQHzA-Q_fb1ETwAAAZPJvn2PEGbbt4_aTcf_0tC-xvwRjXeTRYYARKJS6ZkgH5QVDWqcwMmsv13-vUy_cu37Q7yfDgjRRW8nHxd4uPqQvi6EkF2NLcfuSUx-VbfMwm5kgnFfQrcwIYoHOeMM5VtlmbomuW48IQHBkP_46sLhAwaL3D5KiyrU_ItamrG5HbCkrtaTqgLovTkEhUsK7Umkt2ECKBOJLzTTw7oAjNau1R7hPi6ZLxudK8FsKc5BUyNh43psSZId7Ijc41wd2QScRwS4yhaiu3oJgGSt7tl6ZMuPETaE925hp92c8IGjnXfMF3YqrcrFLnooc2uUT5dunNCR9N6fUTknjqXH/q+A1Ytg==',
    "Upgrade-Insecure-Requests": "1",
}
PROXY_SOURCES = [
    "https://www.sslproxies.org/",
    "https://www.us-proxy.org/",
    "https://free-proxy-list.net/uk-proxy.html",
    "https://free-proxy-list.net/"
]


# --------------------------
# Proxy Fetching Functions
# --------------------------

async def fetch_html(session, url):
    headers = {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }
    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                return await response.text()
    except:
        return None


def extract_proxies(response_text):
    if not response_text:
        return []
    # Common pattern: proxies often appear in <textarea> or a similar block
    textarea_content = re.search(r"<textarea.*?>([\s\S]*?)</textarea>", response_text)
    if not textarea_content:
        return []
    content = textarea_content.group(1)
    proxies = re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}:\d+\b", content)
    return proxies


async def get_proxies_async():
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_html(session, url) for url in PROXY_SOURCES]
        responses = await asyncio.gather(*tasks)
    all_proxies = []
    for resp in responses:
        if resp:
            extracted = extract_proxies(resp)
            selected = extracted[:3]
            all_proxies.extend(selected)
    return all_proxies[:10]


def get_proxies():
    # Run the async proxy fetcher
    return asyncio.run(get_proxies_async())


def get_gemini_response(prompt):
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    return response.text


def get_temp_dir():
    system = platform.system()
    if system == 'Windows':
        temp_dir = os.path.join(os.getenv('LOCALAPPDATA'), 'Temp')
    else:
        raise Exception("Unsupported OS")
    return temp_dir


def get_options():
    chrome_options = Options()
    width = random.randint(1000, 2000)
    height = random.randint(500, 1000)
    chrome_options.add_argument(f"window-size={width},{height}")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.125 Safari/537.36")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument("disable-infobars")
    chrome_options.add_argument('log-level=3')
    return chrome_options


def construct_url(keyword, location):
    keyword_encoded = urllib.parse.quote(keyword)
    location_encoded = urllib.parse.quote(location)
    url = f"https://www.linkedin.com/jobs/search?keywords={keyword_encoded}&location={location_encoded}&position=1&pageNum=0"
    return url


def construct_job_description(soup):
    description_parts = []

    # Extract job title
    title_tag = soup.find('h2', class_='top-card-layout__title')
    title = title_tag.get_text(strip=True) if title_tag else None

    # Extract company name
    company_tag = soup.find('a', class_=re.compile('topcard__org-name-link'))
    company_name = company_tag.get_text(strip=True) if company_tag else None

    # Extract location
    location_tag = soup.find('span', class_='topcard__flavor topcard__flavor--bullet')
    location = location_tag.get_text(strip=True) if location_tag else None

    # Extract job description
    description_tag = soup.find('div', class_='description__text description__text--rich')
    if description_tag:
        text = description_tag.get_text(separator='\n', strip=True).replace('Show more', '').replace('Show less', '')
        description_parts.append(text)

    criteria_tag = soup.find('div', class_='description__job-criteria-list')
    if criteria_tag:
        text = criteria_tag.get_text(separator='\n', strip=True).replace('Show more', '').replace('Show less', '')
        description_parts.append(text)

    concatenated_description = f"Job Title: {title}\nCompany name: {company_name}\nLocation : {location}\n" + '\n'.join(description_parts).strip() if description_parts else None
    return title, company_name, location, concatenated_description


def extract_job_id(job_url):
    """
    Extracts the job ID from a LinkedIn job URL.
    """
    match = re.search(r'-(\d+)\?|/jobs/view/(\d+)', job_url)
    if match:
        return match.group(1) or match.group(2)
    return None


def construct_job_detail_url(url):
    job_id = extract_job_id(url)
    return f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


def construct_pagination_url(original_url, start):
    # Replace '/jobs/' with '/jobs-guest/jobs/api/seeMoreJobPostings/'
    pagination_url = original_url.replace('/jobs/', '/jobs-guest/jobs/api/seeMoreJobPostings/')
    # Add '&start=X' to the URL
    pagination_url += f"&start={start}"
    return pagination_url


def get_title(driver, xpath):
    try:
        return driver.find_element(By.XPATH, xpath).text.strip()
    except (AttributeError, NoSuchElementException) as e:
        print(e)
        return None


def get_salary(driver, xpath):
    try:
        try:
            salary_elem = driver.find_element(By.XPATH, xpath)
        except:
            salary_elem = None
        return salary_elem.text.strip() if salary_elem else ""
    except (AttributeError, NoSuchElementException) as e:
        print(e)
        return None


def get_date(driver, xpath):
    try:
        try:
            date_elem = driver.find_element(By.XPATH, xpath)
        except:
            date_elem = None
        return date_elem.get_attribute("datetime").strip() if date_elem else ""
    except (AttributeError, NoSuchElementException) as e:
        print(e)
        return None


def get_company(driver, xpath):
    try:
        try:
            company_elem = driver.find_element(By.XPATH, xpath)
        except:
            company_elem = None
        return company_elem.text.strip() if company_elem else ""
    except (AttributeError, NoSuchElementException) as e:
        print(e)
        return None


def get_location(driver, xpath):
    try:
        try:
            location_elem = driver.find_element(By.XPATH, xpath)
        except:
            location_elem = None
        return driver.execute_script("return arguments[0].innerText;", location_elem).strip() if location_elem else ""
    except (AttributeError, NoSuchElementException) as e:
        print(e)
        return None


def parse_text_from_html(html_content):
    # Parse the HTML using BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find the section containing the content
    section = soup.find('section', class_='show-more-less-html')

    if not section:
        return ""

    # Replace <br> tags with newline characters
    for br in section.find_all("br"):
        br.replace_with("\n")

    # Process <li> tags to add "● " before the text without adding a newline
    for li in section.find_all("li"):
        li.string = f"● {li.get_text(strip=True)}"

    # Extract and clean the text
    text_content = section.get_text(separator="\n").strip()

    # Remove consecutive newlines
    lines = text_content.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped_line = line.strip()
        if stripped_line:
            cleaned_lines.append(stripped_line)

    return "\n".join(cleaned_lines)


def get_description(driver, xpath):
    try:
        html = driver.execute_script("return arguments[0].innerHTML;", driver.find_element(By.XPATH, xpath))
        return parse_text_from_html(html)
    except (AttributeError, NoSuchElementException) as e:
        print(e)
        return None


def check_exists_by_xpath(driver, xpath):
    try:
        driver.find_element(By.XPATH, xpath)
        return True
    except NoSuchElementException:
        return False


def move_until_found(driver, xpath, count, element_to_click=None, driver_to_click_with=None, previous_anchor=None):
    counter = 0
    while True:
        if check_exists_by_xpath(driver, xpath):
            return 'found'
        if "/jobs/" not in driver.current_url:
            return 'sign_in'
        counter += 1
        if element_to_click and driver_to_click_with and counter % 10 == 0:
            if previous_anchor:
                driver.execute_script("arguments[0].scrollIntoView();", previous_anchor)
                click_forcefully(driver, previous_anchor, True, element_to_click)
            print(f"Reclicking after {counter} attempts")
            driver.execute_script("arguments[0].scrollIntoView();", driver_to_click_with)
            click_forcefully(driver, driver_to_click_with, True, element_to_click)
        if counter >= count:
            # Quit everything and start over again
            raise Exception("Element not found within the count limit, restarting...")
        time.sleep(random.uniform(0.1, 0.5))


def click_forcefully(driver, element, limit, xpath):
    counter = 0
    while True:
        try:
            driver.execute_script("arguments[0].click();", element)
            if check_exists_by_xpath(driver, xpath):
                return True
        except Exception as e:
            print(e)
            pass
        counter += 1
        if limit and counter >= 50:
            return False


def kill_chrome_processes():
    # Iterate over all running processes
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            # Check if process name contains "chrome"
            if 'chrome' in proc.info['name'].lower():
                # Terminate the process
                proc.kill()
                print(f"Killed process {proc.info['name']} with PID {proc.info['pid']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass


def clear_recent_temp_files(temp_dir, age_minutes=2):
    current_time = time.time()
    age_seconds = age_minutes * 60

    for root, dirs, files in os.walk(temp_dir):
        for name in files + dirs:
            full_path = os.path.join(root, name)
            try:
                # Get the creation time of the file/directory
                creation_time = os.path.getctime(full_path)

                # Check if the file/directory was created within the last 'age_minutes' minutes
                if (current_time - creation_time) < age_seconds:
                    if os.path.isfile(full_path) or os.path.islink(full_path):
                        os.remove(full_path)
                    elif os.path.isdir(full_path):
                        shutil.rmtree(full_path)
                    print(f"Deleted: {full_path}")
            except Exception as e:
                print(f"Failed to delete {full_path}. Reason: {e}")


def kill_chrome(driver):
    try:
        driver.close()
        driver.quit()
    except Exception as e:
        print(f"Error closing driver: {e}")
    # kill_chrome_processes()
    # clear_recent_temp_files(get_temp_dir(), age_minutes=200)


def construct_prompt_without_score(jobs_data):
    # Define the JSON format matching the Django model

    json_format = {
        "title": "string",
        "description": "string",
        "requirements": "list of strings (try extracting requirements from the description if they're not clearly listed, don't list required hard skills, but other contextual requirements if found)",
        "company_name": "string",
        "company_size": "integer (set null if it's not available)",
        "location": "string (set null if it's not available)",
        "employment_type": "string (choices: 'remote', 'hybrid', 'on-site')",
        "linkedin_profiles": "list of strings (set null if they're not available)",
        "original_url": "string (URL)",
        "salary_range": "string (write the string as it, set null if it's not available)",
        "min_salary": "string (the minimum salary can be found in the salary_range, get the number only without adding any alpha character. set null if it's not available, and if there was only one number and not a range, extract it here)",
        "max_salary": "string (the maximum salary can be found in the salary_range, get the number only without adding any alpha character. set null if it's not available, and if there was only one number and not a range, extract it here)",
        "benefits": "list of strings (set null if they're not available)",
        "skills_required": "list of strings (try extracting skills from the description if they're not clearly listed. Only focus on technical skills and soft skills, avoid general hard skills such as 'Software Development', they need to be specific)",
        "posted_date": "string (date in YYYY-MM-DD format, set null if it's not available)",
        "industry": "string (set null if it's not available)",
        "job_type": "string (choices: 'full-time', 'part-time', 'contract', 'freelance', 'CDD', 'CDI', 'other')",
    }
    prompt = f"""
    You are provided with a list of job postings.

    **Instructions:**

    - Rewrite the job description in a more structured manner to avoid duplication of the original text.
    - Extract all available data from the job postings.
    - Respond with a JSON array containing objects for each job, following the specified JSON format below.
    - Do not include any comments or explanations in your response. Only provide the JSON array.

    **JSON Format:**

    {json.dumps(json_format, indent=4)}

    **Job Postings:**

    {json.dumps(jobs_data, indent=4, ensure_ascii=False)}

    **Please provide the JSON array as your response, without adding any comment, or using an editor. Only the JSON.**
    """
    return prompt


def construct_prompt(candidate_profile, jobs_data):
    # Define the JSON format matching the Django model

    json_format = {
        "title": "string",
        "description": "string",
        "requirements": "list of strings (try extracting requirements from the description if they're not clearly listed, don't list required hard skills, but other contextual requirements if found)",
        "company_name": "string",
        "company_size": "integer (set null if it's not available)",
        "location": "string (set null if it's not available)",
        "employment_type": "string (choices: 'remote', 'hybrid', 'on-site')",
        "linkedin_profiles": "list of strings (set null if they're not available)",
        "original_url": "string (URL)",
        "salary_range": "string (write the string as it, set null if it's not available)",
        "min_salary": "string (the minimum salary can be found in the salary_range, get the number only without adding any alpha character. set null if it's not available, and if there was only one number and not a range, extract it here)",
        "max_salary": "string (the maximum salary can be found in the salary_range, get the number only without adding any alpha character. set null if it's not available, and if there was only one number and not a range, extract it here)",
        "benefits": "list of strings (set null if they're not available)",
        "skills_required": "list of strings (try extracting skills from the description if they're not clearly listed. Only focus on technical skills and soft skills, avoid general hard skills such as 'Software Development', they need to be specific)",
        "posted_date": "string (date in YYYY-MM-DD format, set null if it's not available)",
        "industry": "string (set null if it's not available)",
        "job_type": "string (choices: 'full-time', 'part-time', 'contract', 'freelance', 'CDD', 'CDI', 'other')",
        "score": "float (matching score out of 100, with decimals for granularity, it shouldn't be null under any circumstance)"
    }
    prompt = f"""
    You are provided with a candidate's profile in JSON format and a list of job postings. Your task is to compare the candidate's profile with each job and assign a matching score based on the following refined criteria:

    1. **Job Title Match (10 points):**
       - **10 points:** Candidate's job title is the exact same as the job title in the job description.
       - **7.5 points:** Candidate's job title is a recognized variation of the job title in the job description.
       - **5 points:** Candidate's job title and the job's title are not identical but are very closely related in function, duties, or industry focus (e.g., "Fullstack Developer" vs "Software Engineer").
       - **2.5 points:** Candidate's job title is somewhat related, still within the same broader industry or domain.
       - **0 points:** Candidate's job title is in a completely different industry or nature than the job title in the job description.
    
    2. **Location Match (10 points):**
       - **10 points:** Candidate's city matches the job location, or the job is remote.
       - **7.5 points:** Candidate's city is within the same region or state as the job.
       - **5 points:** Candidate's city is within the same country as the job.
       - **2.5 points:** Candidate's country differs, but the job allows relocation.
       - **0 points:** Location is different with no indication of remote or relocation.
    
    3. **Experience Match (20 points):**
       - Calculate the percentage of the required experience that the candidate meets.
       - **Points Awarded:** `(Candidate_Years_of_Experience / Required_Years_of_Experience) * 20`, capped at 20.
    
    4. **Skills Match (30 points):**
       - Compare required skills to candidate's skills (both hard and soft).
       - **Points Awarded:** `(Number_of_Matching_Skills / Total_Required_Skills) * 30`
    
    5. **Education Match (10 points):**
       - **10 points:** Candidate's education level exceeds the requirement.
       - **8 points:** Education level meets the requirement.
       - **5 points:** Slightly below the requirement.
       - **0 points:** Does not meet the requirement.
    
    6. **Role Requirements Match (10 points):**
       - Assess how the candidate's past responsibilities and achievements align with the job's responsibilities.
       - **Points Awarded:** `(Relevance_Percentage) * 10`
    
    7. **Language Proficiency (5 points):**
       - **5 points:** Candidate fully meets language requirements.
       - **2-4 points:** Candidate partially meets them.
       - **0 points:** Candidate does not meet language requirements.
    
    8. **Additional Criteria (5 points):**
       - Consider certifications, interests, projects, volunteering, and other relevant factors.
       - **Points Awarded:** `(Relevance_Percentage) * 5`

    **Instructions:**

    - For each job, calculate the total score out of 100 points, allowing for decimal values down to .001 to increase granularity. Please be as strict and accurate as possible following the specified criteria. 
    - Rewrite the job description in a more structured manner to avoid duplication of the original text.
    - Extract all available data from the job postings.
    - Respond with a JSON array containing objects for each job, following the specified JSON format below.
    - Add a key called "score" in each job's object, representing the matching score (use a float value for precision).
    - Do not include any comments or explanations in your response. Only provide the JSON array.
    
    **JSON Format:**

    {json.dumps(json_format, indent=4)}

    **Candidate Profile:**

    {json.dumps(candidate_profile, indent=4, ensure_ascii=False)}

    **Job Postings:**

    {json.dumps(jobs_data, indent=4, ensure_ascii=False)}

    **Please provide the JSON array as your response, without adding any comment, or using an editor. Only the JSON.**
    """
    return prompt


def scrape_jobs(keyword, location, num_jobs_to_scrape):
    # Read candidate profile
    partial_jobs_collected = []
    total_jobs_collected = []
    anchors_processed = set()

    # Construct the search URL
    multiple_jobs_url = construct_url(keyword, location)

    # Headers for the HTTP requests
    multiple_jobs_headers = {
        "User-Agent": f"Mozilla/5.0 (Windows NT {random.randint(6, 10)}.{random.randint(0, 3)}; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(80, 95)}.0.{random.randint(3000, 4000)}.{random.randint(100, 150)} Safari/537.36",
        "Accept": Cookies["Accept"],
        "Cookie": Cookies["Cookie"],
        "Upgrade-Insecure-Requests": Cookies["Upgrade-Insecure-Requests"],
    }

    def fetch_page_with_retry(url, headers, substring, max_retries=50):
        for _ in range(max_retries):
            r = requests.get(url, headers=headers)
            if substring in r.text:
                return r.text
            else:
                sleep_time = random.uniform(0, 3)
                time.sleep(sleep_time)
        return None

    # Fetch and parse the job listings
    jobs_data = []

    # Fetch the initial page
    print(multiple_jobs_url)
    initial_page_text = fetch_page_with_retry(multiple_jobs_url, multiple_jobs_headers, "job-search-card__listdate", 50)
    if initial_page_text is None:
        print("Failed to fetch initial page.")
        return

    # Parse the initial page
    soup = BeautifulSoup(initial_page_text, 'html.parser')
    job_listings = soup.find_all('li')

    # Get already scraped jobs (based on Job table)
    already_scraped_urls = Job.objects.values_list('original_url', flat=True)

    # Extract total number of jobs from the title
    title_tag = soup.find('title')
    if title_tag:
        title_text = title_tag.get_text()
        match = re.search(r'(\d+)', title_text.replace(',', ''))
        if match:
            total_jobs = int(match.group(1))
        else:
            total_jobs = len(job_listings)
    else:
        total_jobs = len(job_listings)

    total_jobs = max(MAX_TOTAL, total_jobs)

    # Calculate start values for pagination
    start_values = list(range(0, total_jobs, 25))

    # Function to process job listings from a page
    def process_job_listings(soup):
        job_listings = soup.find_all('li')
        for li in job_listings:
            base_card = li.find('div', class_='base-card')
            if base_card:
                # Extract the href
                a_tag = base_card.find('a', class_='base-card__full-link')
                if a_tag and 'href' in a_tag.attrs:
                    job_url = a_tag['href']
                    if not job_url.startswith('http'):
                        job_url = 'https://www.linkedin.com' + job_url
                    # Avoid duplicates
                    job_url_no_query = job_url.split("?")[0]
                    if job_url_no_query in anchors_processed or job_url_no_query in already_scraped_urls:
                        continue
                    anchors_processed.add(job_url_no_query)
                    # Extract datetime
                    time_tag = base_card.find('time', class_=re.compile('job-search-card__listdate'))
                    job_datetime_str = None
                    if time_tag and 'datetime' in time_tag.attrs:
                        job_datetime_str = time_tag['datetime']
                    jobs_data.append({'url': job_url, 'date': job_datetime_str})

    # Process initial page
    # process_job_listings(soup)

    # Fetch additional pages
    for start in start_values:
        # Construct paginated URL with adjusted path
        paginated_url = construct_pagination_url(multiple_jobs_url, start)
        page_text = fetch_page_with_retry(paginated_url, multiple_jobs_headers, "job-search-card__listdate", 50)
        if page_text:
            # The response is expected to be HTML snippets, so we can parse it directly
            soup = BeautifulSoup(page_text, 'html.parser')
            process_job_listings(soup)
        else:
            print(f"Failed to fetch page with start={start}")

    # Now we have collected all jobs from the search results
    # Sort jobs by date if needed
    jobs_data.sort(key=lambda x: x['date'] or datetime.min, reverse=True)

    # Now limit jobs_data to num_jobs_to_scrape
    if len(jobs_data) > num_jobs_to_scrape:
        jobs_data = jobs_data[:num_jobs_to_scrape]

    # Now, fetch job details

    async def fetch_job_detail(session, url, substring, max_retries=50):
        for _ in range(max_retries):
            try:
                single_job_headers = {
                    "User-Agent": ua.random,
                    "Accept": Cookies["Accept"],
                    "Cookie": Cookies["Cookie"],
                    "Upgrade-Insecure-Requests": Cookies["Upgrade-Insecure-Requests"],
                }
                async with session.get(url, headers=single_job_headers) as response:
                    text = await response.text()
                    if substring in text:
                        return text
                    else:
                        sleep_time = random.uniform(3, 15)
                        await asyncio.sleep(sleep_time)
            except Exception:
                sleep_time = random.uniform(3, 15)
                await asyncio.sleep(sleep_time)
        return None

    async def process_job(session, job):
        # Construct the new job detail URL
        job_detail_url = construct_job_detail_url(job['url'])
        if not job_detail_url:
            return
        job_detail_text = await fetch_job_detail(session, job_detail_url, "top-card-layout__title", 100)
        if job_detail_text:
            # Parse the job detail page
            job_soup = BeautifulSoup(job_detail_text, 'html.parser')
            # Extract required data
            title, company_name, loc, description = construct_job_description(job_soup)
            # Collect data
            job['title'] = title
            job['company_name'] = company_name
            job['location'] = location
            job['description'] = description
            job['original_url'] = job['url']
            partial_jobs_collected.append(job)
            total_jobs_collected.append(job)

            print(f"Title: {title}")
            print(f"Company: {company_name}")
            print(f"Location: {location}")
            print(f"Description: {description}")
            print(f"Posted Date: {job['date'] if job['date'] else 'N/A'}")
            print(f"Job URL: {job['url']}")
            print("-" * 80)

            # Process jobs in batches and send to Gemini
            if len(partial_jobs_collected) == BATCH_SIZE:
                for i in range(0, len(partial_jobs_collected), BATCH_SIZE):
                    jobs_batch = partial_jobs_collected[i:i + BATCH_SIZE]
                    prompt = construct_prompt_without_score(jobs_batch)
                    gemini_response = get_gemini_response(prompt)
                    if "```" in gemini_response:
                        gemini_response = (gemini_response.split("```json")[-1]).split("```")[0]
                    try:
                        jobs_with_scores = json.loads(gemini_response)
                        print("Gemini Response:")
                        print(json.dumps(jobs_with_scores, indent=4, ensure_ascii=False))
                        # Create jobs and job searches in the database
                        # for job_data in jobs_with_scores:
                        #     await process_and_save_job(job_data)
                        await asyncio.gather(
                            *(process_and_save_job(job_data) for job_data in jobs_with_scores)
                        )
                        partial_jobs_collected.clear()  # Clear the processed batch
                    except json.JSONDecodeError as e:
                        print(f"Error parsing Gemini response: {e}")
                        print("Gemini response was:")
                        print(gemini_response)
        else:
            print(f"Failed to fetch job detail for URL: {job_detail_url}")

    async def main(jobs_data):
        semaphore = asyncio.Semaphore(10)
        async with aiohttp.ClientSession() as session:
            tasks = []
            for job in jobs_data:
                task = asyncio.ensure_future(bound_process_job(semaphore, session, job))
                tasks.append(task)
            await asyncio.gather(*tasks)

    async def bound_process_job(semaphore, session, job):
        async with semaphore:
            await process_job(session, job)

    # Run the main function to fetch job details
    asyncio.run(main(jobs_data))

    print("Scraping completed successfully.")
    return total_jobs_collected


def is_valid_job_url(url):
    """
    Validates if the URL belongs to an allowed domain and matches the job link indicator.
    """
    parsed_url = urllib.parse.urlparse(url)
    domain = parsed_url.netloc
    path = parsed_url.path

    for allowed_domain, job_indicator in ALLOWED_JOB_DOMAINS.items():
        if allowed_domain in domain and job_indicator in path:
            return True
    return False


def fetch_description(url, proxy=None):
    headers = {
        "User-Agent": ua.random,
        "Accept": Cookies["Accept"],
        "Cookie": Cookies["Cookie"],
        "Upgrade-Insecure-Requests": Cookies["Upgrade-Insecure-Requests"]
    }
    proxies = None
    if proxy:
        proxies = {
            "http": proxy,
            "https": proxy
        }
    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=3)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Assuming construct_job_description returns (_, _, _, description)
            _, _, _, description = construct_job_description(soup)
            return description
    except:
        pass
    return None


def fetch_job_description(url, max_retries=100):
    for _ in range(max_retries):
        # Fetch new proxies every retry
        proxies = get_proxies()
        job_detail_url = construct_job_detail_url(url)

        # Use a ThreadPoolExecutor to run requests concurrently
        with ThreadPoolExecutor(max_workers=11) as executor:
            futures = []
            # 20 with proxies
            for p in proxies:
                futures.append(executor.submit(fetch_description, job_detail_url, p))
            # 1 without proxy
            futures.append(executor.submit(fetch_description, job_detail_url, None))

            # As soon as one completes, check result
            for future in as_completed(futures):
                result = future.result()
                if result:
                    # We got a successful description
                    return result

        # If we reach here, no success in this retry
        # Wait and try again
        time.sleep(random.uniform(3, 15))

    # If no success after all retries
    return None


def construct_tailored_job_prompt(cv_data_instance, candidate, job_description):
    if cv_data_instance:
        # Use the name from the existing CVData if available
        name = cv_data_instance.name if cv_data_instance.name else f"{candidate.first_name} {candidate.last_name}"
        # Determine which fields are missing
        missing_fields = {
            "age": cv_data_instance.age,
            "work": cv_data_instance.work,
            "educations": cv_data_instance.educations,
            "projects": cv_data_instance.projects,
            "interests": cv_data_instance.interests,
            "certifications": cv_data_instance.certifications,
        }

        # Construct the prompt to ask for missing fields only
        prompt = f"""
            You are tasked with generating a JSON representation of a resume based on a job description.
            The resume should intelligently match the job requirements, but you should not copy the job description verbatim.
            Instead, create a resume that fits the job's requirements by tailoring certain fields appropriately.

            Follow the instructions indicated below for each field :

            **Skills**: Include a list of relevant hard skills based on the job description, replacing the original skills in the profile with the ones mentioned in the job description intelligently in a way that aligns with the candidate's experience and education. Hard skills emphasized in the job description should have an advanced level, while others can have an intermediate level to retain a realistic skill set, and ALL skills should be written in the language of the job description.
            **Social**: Include a list of relevant soft skills based on the job description, written in the language of the job description.
            **Languages**: Include any languages that could be relevant for the job, written in the language of the job description.
            **Summary**: Write a brief summary that showcases the candidate as a good fit for the role without making any false claims, nor mentioning the company name. Write the summary in the language of the job description.
            **Age**: Leave age value as I passed it without any change.
            **Work**: If the language of the job description matched the language of work experiences I passed (assuming that I passed it non-empty, otherwise leave it empty), reformulate work experiences with putting an emphasis on areas that corresponds with the job, without adding or removing anything, just reformulating. And if the job description was in a different language, translate work experiences text to that language.
            **Educations**: If the language of the job description matched the language of educations I passed (assuming that I passed it non-empty, otherwise leave it empty), leave educations text as I passed it, and if it didn't match the language, translate educations to the language of the job description.
            **Projects**: If the language of the job description matched the language of projects I passed (assuming that I passed it non-empty, otherwise leave it empty), leave projects text as I passed it, and if it didn't match the language, translate projects to the language of the job description.
            **Certifications**: If the language of the job description matched the language of certifications I passed (assuming that I passed it non-empty, otherwise leave it empty), leave certifications text as I passed it, and if it didn't match the language, translate certifications to the language of the job description.
            **Interests**: If the language of the job description matched the language of interests I passed (assuming that I passed it non-empty, otherwise leave it empty), leave interests text as I passed it, and if it didn't match the language, translate interests to the language of the job description.

            If a city or country is found in the job description, use it as the candidate's location.

            Return the data as a JSON with the following structure:
            {{
                "title": "<job_title>",
                "name": "{name}",
                "email": "{candidate.user.email}",
                "phone": "{candidate.phone}",
                "age": {missing_fields['age']},
                "city": "<city>",
                "work": {missing_fields['work']},
                "educations": {missing_fields['educations']},
                "projects": {missing_fields['projects']},
                "interests": {missing_fields['interests']},
                "certifications": {missing_fields['certifications']},
                "languages": [
                    {{
                        "language": "<language_name>",
                        "level": "<proficiency>"
                    }}
                ],
                "skills": [
                    {{
                        "skill": "<hard_skill_name>",
                        "level": "<hard_skill_level>"
                    }}
                ],
                "social": [
                    {{
                        "skill": "<soft_skill_name>"
                    }}
                ],
                "headline": null,
                "summary": "<tailored_summary>"
            }}

            Here is the job description:
            {job_description}
        """
    else:
        # Construct the full prompt if no CVData exists
        prompt = f"""
            You are tasked with generating a JSON representation of a resume based on a job description.
            The resume should intelligently match the job requirements, but you should not copy the job description verbatim.
            Instead, create a resume that fits the job's requirements by tailoring certain fields appropriately.

            You must leave the work experiences and education fields empty, as these should be filled only by the candidate.
            However, you should intelligently fill the following fields to fit the job description:

            **Skills**: Include a list of relevant hard skills based on the job description, ensuring they align with the requirements without exaggerating. Hard skills emphasized in the job description should have an advanced level, while others can have an intermediate level to retain a realistic skill set.
            **Social**: Include a list of relevant soft skills based on the job description.
            **Languages**: Include any languages that could be relevant for the job.
            **Summary**: Write a brief summary that showcases the candidate as a good fit for the role without making any false claims.

            If a city or country is found in the job description, use it as the candidate's location.

            Return the data as a JSON with the following structure:
            {{
                "title": "<job_title>",
                "name": "{candidate.first_name} {candidate.last_name}",
                "email": "{candidate.user.email}",
                "phone": "{candidate.phone}",
                "age": null,
                "city": "<city>",
                "work": [],
                "educations": [],
                "languages": [
                    {{
                        "language": "<language_name>",
                        "level": "<proficiency>"
                    }}
                ],
                "skills": [
                    {{
                        "skill": "<hard_skill_name>",
                        "level": "<hard_skill_level>"
                    }}
                ],
                "social": [
                    {{
                        "skill": "<soft_skill_name>"
                    }}
                ],
                "headline": null,
                "summary": "<tailored_summary>"
            }}
            
            Here is the job description:
            {job_description}
        """

    return prompt


def construct_candidate_profile(cv_data):
    """
    Constructs a JSON representation of the candidate's CV data for Gemini.
    """
    # Fetch CVData associated with the given CV
    # cv_data = CVData.objects.filter(cv=cv).first()

    # Serialize CVData if available
    if cv_data:
        serialized_cv_data = CVDataSerializer(cv_data).data
    else:
        serialized_cv_data = {field: None for field in CVDataSerializer.Meta.fields}
    return serialized_cv_data


def construct_single_job_prompt(candidate_profile, job_description, job_url):
    """
    Constructs a prompt for scoring a single job based on the candidate's profile.
    """
    json_format = {
        "title": "string",
        "description": "string",
        "requirements": "list of strings (try extracting requirements from the description if they're not clearly listed, don't list required hard skills, but other contextual requirements if found)",
        "company_name": "string",
        "company_size": "integer (set null if it's not available)",
        "location": "string (set null if it's not available)",
        "employment_type": "string (choices: 'remote', 'hybrid', 'on-site')",
        "linkedin_profiles": "list of strings (set null if they're not available)",
        "original_url": "string (URL)",
        "salary_range": "string (write the string as it, set null if it's not available)",
        "min_salary": "string (the minimum salary can be found in the salary_range, get the number only without adding any alpha character. set null if it's not available, and if there was only one number and not a range, extract it here)",
        "max_salary": "string (the maximum salary can be found in the salary_range, get the number only without adding any alpha character. set null if it's not available, and if there was only one number and not a range, extract it here)",
        "benefits": "list of strings (set null if they're not available)",
        "skills_required": "list of strings (try extracting all skills from the description. Only focus on technical skills and soft skills, avoid general hard skills such as 'Software Development', they need to be specific)",
        "posted_date": "string (date in YYYY-MM-DD format, set null if it's not available)",
        "industry": "string (set null if it's not available)",
        "job_type": "string (choices: 'full-time', 'part-time', 'contract', 'freelance', 'CDD', 'CDI', 'other')",
        "score": "float (matching score out of 100, with decimals for granularity, it shouldn't be null under any circumstance)"
    }

    prompt = f"""
    You are provided with a candidate's profile in JSON format and a single job posting. Your task is to compare the candidate's profile with the job and assign a matching score based on the following refined criteria:

    1. **Job Title Match (10 points):**
       - **10 points:** Candidate's job title is the exact same as the job title in the job description.
       - **7.5 points:** Candidate's job title is a recognized variation of the job title in the job description.
       - **5 points:** Candidate's job title and the job's title are not identical but are very closely related in function, duties, or industry focus (e.g., "Fullstack Developer" vs "Software Engineer").
       - **2.5 points:** Candidate's job title is somewhat related, still within the same broader industry or domain.
       - **0 points:** Candidate's job title is in a completely different industry or nature than the job title in the job description.
    
    2. **Location Match (10 points):**
       - **10 points:** Candidate's city matches the job location, or the job is remote.
       - **7.5 points:** Candidate's city is within the same region or state as the job.
       - **5 points:** Candidate's city is within the same country as the job.
       - **2.5 points:** Candidate's country differs, but the job allows relocation.
       - **0 points:** Location is different with no indication of remote or relocation.
    
    3. **Experience Match (20 points):**
       - Calculate the percentage of the required experience that the candidate meets.
       - **Points Awarded:** `(Candidate_Years_of_Experience / Required_Years_of_Experience) * 20`, capped at 20.
    
    4. **Skills Match (30 points):**
       - Compare required skills to candidate's skills (both hard and soft).
       - **Points Awarded:** `(Number_of_Matching_Skills / Total_Required_Skills) * 30`
    
    5. **Education Match (10 points):**
       - **10 points:** Candidate's education level exceeds the requirement.
       - **8 points:** Education level meets the requirement.
       - **5 points:** Slightly below the requirement.
       - **0 points:** Does not meet the requirement.
    
    6. **Role Requirements Match (10 points):**
       - Assess how the candidate's past responsibilities and achievements align with the job's responsibilities.
       - **Points Awarded:** `(Relevance_Percentage) * 10`
    
    7. **Language Proficiency (5 points):**
       - **5 points:** Candidate fully meets language requirements.
       - **2-4 points:** Candidate partially meets them.
       - **0 points:** Candidate does not meet language requirements.
    
    8. **Additional Criteria (5 points):**
       - Consider certifications, interests, projects, volunteering, and other relevant factors.
       - **Points Awarded:** `(Relevance_Percentage) * 5`

   
    **Instructions:**

    - Calculate the total score out of 100 points, allowing for decimal values down to .001 to increase granularity. Please be as strict and accurate as possible following the specified criteria.
    - Rewrite the job description in a more structured manner to avoid duplication of the original text.
    - Extract all available data from the job posting.
    - Respond with a JSON object following the specified JSON format below.
    - Add a key called "score" in the object, representing the matching score (use a float value for precision).
    - Do not include any comments or explanations in your response. Only provide the JSON object.

    **JSON Format:**

    {json.dumps(json_format, indent=4)}

    **Candidate Profile:**

    {json.dumps(candidate_profile, indent=4, ensure_ascii=False)}

    **Job Posting:**

    {{
        "url": "{job_url}",x
        "description": "{job_description}"
    }}

    **Please provide the JSON object as your response, without adding any comment, or using an editor. Only the JSON.**
    """
    return prompt


def has_sufficient_credits(candidate, action_name):
    try:
        credit_action = CreditAction.objects.get(action_name=action_name)
    except CreditAction.DoesNotExist:
        raise ValueError(f"Action '{action_name}' is not defined in CreditAction.")

    if candidate.credits < credit_action.credit_cost:
        return False, credit_action.credit_cost
    return True, credit_action.credit_cost


def deduct_credits(candidate, action_name):
    sufficient, credit_cost = has_sufficient_credits(candidate, action_name)
    if not sufficient:
        return False, credit_cost

    # Deduct the required credits
    candidate.credits -= credit_cost
    candidate.save()
    return True, credit_cost


def construct_only_score_job_prompt(candidate_profile, job_description):
    """
    Construct a prompt asking Gemini to only calculate the similarity score.
    """
    prompt = f"""
    You are provided with a candidate's profile in JSON format and a job description.
    Your task is to calculate the similarity score based on the following refined criteria:

    1. **Job Title Match (10 points):**
       - **10 points:** Candidate's job title is the exact same as the job title in the job description.
       - **7.5 points:** Candidate's job title is a recognized variation of the job title in the job description.
       - **5 points:** Candidate's job title and the job's title are not identical but are very closely related in function, duties, or industry focus (e.g., "Fullstack Developer" vs "Software Engineer").
       - **2.5 points:** Candidate's job title is somewhat related, still within the same broader industry or domain.
       - **0 points:** Candidate's job title is in a completely different industry or nature than the job title in the job description.
    
    2. **Location Match (10 points):**
       - **10 points:** Candidate's city matches the job location, or the job is remote.
       - **7.5 points:** Candidate's city is within the same region or state as the job.
       - **5 points:** Candidate's city is within the same country as the job.
       - **2.5 points:** Candidate's country differs, but the job allows relocation.
       - **0 points:** Location is different with no indication of remote or relocation.
    
    3. **Experience Match (20 points):**
       - Calculate the percentage of the required experience that the candidate meets.
       - **Points Awarded:** `(Candidate_Years_of_Experience / Required_Years_of_Experience) * 20`, capped at 20.
    
    4. **Skills Match (30 points):**
       - Compare required skills to candidate's skills (both hard and soft).
       - **Points Awarded:** `(Number_of_Matching_Skills / Total_Required_Skills) * 30`
    
    5. **Education Match (10 points):**
       - **10 points:** Candidate's education level exceeds the requirement.
       - **8 points:** Education level meets the requirement.
       - **5 points:** Slightly below the requirement.
       - **0 points:** Does not meet the requirement.
    
    6. **Role Requirements Match (10 points):**
       - Assess how the candidate's past responsibilities and achievements align with the job's responsibilities.
       - **Points Awarded:** `(Relevance_Percentage) * 10`
    
    7. **Language Proficiency (5 points):**
       - **5 points:** Candidate fully meets language requirements.
       - **2-4 points:** Candidate partially meets them.
       - **0 points:** Candidate does not meet language requirements.
    
    8. **Additional Criteria (5 points):**
       - Consider certifications, interests, projects, volunteering, and other relevant factors.
       - **Points Awarded:** `(Relevance_Percentage) * 5`

    **Instructions:**
    - Calculate the total score out of 100.
    - Respond with a JSON object containing only the "score" key.

    **Candidate Profile:**
    {json.dumps(CVDataSerializer(candidate_profile).data, indent=4, ensure_ascii=False)}

    **Job Description:**
    {job_description}
    """
    return prompt


@sync_to_async
def process_and_save_job(job_data):
    """
    Process and save a single job using Django ORM.
    """
    job_url_no_query = job_data['original_url'].split("?")[0]
    job_id = extract_job_id(job_data['original_url'])

    if not job_id:
        return None

    # Check if a job with the same job_id already exists
    existing_job = Job.objects.filter(job_id=job_id).first()

    if existing_job:
        return None  # Skip creating a duplicate job with the same ID

    # Check for jobs with the same title, company_name, and location
    existing_similar_jobs = Job.objects.filter(
        title=job_data['title'],
        company_name=job_data['company_name'],
        location=job_data['location']
    )

    if existing_similar_jobs.exists():
        for similar_job in existing_similar_jobs:
            # Check if the posted_date matches
            if similar_job.posted_date == datetime.strptime(job_data['posted_date'], '%Y-%m-%d').date():
                return None  # Skip creating a duplicate job with the same attributes

            # Check if the new job's posted_date is more recent
            if job_data.get('posted_date') and similar_job.posted_date:
                if datetime.strptime(job_data['posted_date'], '%Y-%m-%d').date() > similar_job.posted_date:
                    # Remove the older job
                    similar_job.delete()

    # Create a new job if no duplicate or outdated jobs are found
    Job.objects.create(
        title=job_data['title'],
        description=job_data['description'],
        company_name=job_data['company_name'],
        location=job_data['location'],
        salary_range=job_data.get('salary_range'),
        min_salary=job_data.get('min_salary'),
        max_salary=job_data.get('max_salary'),
        employment_type=job_data.get('employment_type', 'full-time'),
        original_url=job_url_no_query,
        skills_required=job_data['skills_required'],
        requirements=job_data['requirements'],
        benefits=job_data['benefits'],
        posted_date=job_data.get('posted_date'),
        job_id=job_id
    )


def construct_similarity_prompt(candidate_profile, jobs_data):
    """
    Constructs a prompt for getting similarity scores between a candidate's profile and a list of jobs.
    """
    prompt = f"""
    You are provided with a candidate's profile in JSON format and a list of job postings. Your task is to compare the candidate's profile with each job and assign a matching score based on the following refined criteria:

    1. **Job Title Match (10 points):**
       - **10 points:** Candidate's job title is the exact same as the job title in the job description.
       - **7.5 points:** Candidate's job title is a recognized variation of the job title in the job description.
       - **5 points:** Candidate's job title and the job's title are not identical but are very closely related in function, duties, or industry focus (e.g., "Fullstack Developer" vs "Software Engineer").
       - **2.5 points:** Candidate's job title is somewhat related, still within the same broader industry or domain.
       - **0 points:** Candidate's job title is in a completely different industry or nature than the job title in the job description.
    
    2. **Location Match (10 points):**
       - **10 points:** Candidate's city matches the job location, or the job is remote.
       - **7.5 points:** Candidate's city is within the same region or state as the job.
       - **5 points:** Candidate's city is within the same country as the job.
       - **2.5 points:** Candidate's country differs, but the job allows relocation.
       - **0 points:** Location is different with no indication of remote or relocation.
    
    3. **Experience Match (20 points):**
       - Calculate the percentage of the required experience that the candidate meets.
       - **Points Awarded:** `(Candidate_Years_of_Experience / Required_Years_of_Experience) * 20`, capped at 20.
    
    4. **Skills Match (30 points):**
       - Compare required skills to candidate's skills (both hard and soft).
       - **Points Awarded:** `(Number_of_Matching_Skills / Total_Required_Skills) * 30`
    
    5. **Education Match (10 points):**
       - **10 points:** Candidate's education level exceeds the requirement.
       - **8 points:** Education level meets the requirement.
       - **5 points:** Slightly below the requirement.
       - **0 points:** Does not meet the requirement.
    
    6. **Role Requirements Match (10 points):**
       - Assess how the candidate's past responsibilities and achievements align with the job's responsibilities.
       - **Points Awarded:** `(Relevance_Percentage) * 10`
    
    7. **Language Proficiency (5 points):**
       - **5 points:** Candidate fully meets language requirements.
       - **2-4 points:** Candidate partially meets them.
       - **0 points:** Candidate does not meet language requirements.
    
    8. **Additional Criteria (5 points):**
       - Consider certifications, interests, projects, volunteering, and other relevant factors.
       - **Points Awarded:** `(Relevance_Percentage) * 5`


    **Instructions:**
    - For each job, calculate the total score out of 100 points, allowing for decimal values down to .001 to increase granularity. Please be as strict and accurate as possible following the specified criteria. 
    - Respond with a JSON array containing objects for each job, including only the job ID and the calculated score.

    **JSON Format:**
    [
        {{
            "id": "integer (the unique ID of the job)",
            "score": "float (matching score out of 100, with decimals for granularity)"
        }}
    ]

    **Candidate Profile:**
    {json.dumps(candidate_profile, indent=4, ensure_ascii=False)}

    **Job Postings:**
    {json.dumps(jobs_data, indent=4, ensure_ascii=False)}

    **Please provide the JSON array as your response, without adding any comments or explanations. Only the JSON.**
    """
    return prompt


def generate_cv_pdf(cv):
    """
    Generates and saves a PDF for the given CV instance and creates a thumbnail.
    Removes any previously generated files for the CV.
    """
    if not cv.cv_data or not cv.template:
        raise ValueError("CV must have both data and template to generate PDF")

    # URL for the frontend resume preview
    url = f"{FRONTEND_PREVIEW_URL}{cv.id}"
    print(url)
    chrome_options = get_options()
    driver = None

    try:
        chromedriver_autoinstaller.install()
        driver = webdriver.Chrome(options=chrome_options)
        driver.get("chrome://settings/clearBrowserData")  # Open Chrome's clear cache settings
        driver.execute_script("window.localStorage.clear();")  # Clear local storage
        driver.execute_script("window.sessionStorage.clear();")  # Clear session storage
        driver.execute_cdp_cmd("Network.clearBrowserCache", {})  # Clear browser cache using DevTools Protocol
        driver.execute_cdp_cmd("Network.clearBrowserCookies", {})  # Clear cookies for safety

        driver.get(url)

        # Wait for the container to appear
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "container"))
            )
        except TimeoutException:
            raise ValueError("Page did not load correctly, container not found within the time limit.")

        # Generate the PDF data as a base64-encoded string
        response = driver.execute_cdp_cmd("Page.printToPDF", {
            "printBackground": True,
            "preferCSSPageSize": True,
            "displayHeaderFooter": False
        })
        pdf_data = base64.b64decode(response['data'])

        # Remove previous files if they exist
        # if cv.generated_pdf:
        #     print(cv.generated_pdf)
        #     old_pdf_path = os.path.join(settings.MEDIA_ROOT, cv.generated_pdf.name)
        #     if os.path.exists(old_pdf_path):
        #         os.remove(old_pdf_path)
        #
        # if cv.thumbnail:
        #     print(cv.thumbnail)
        #     old_thumbnail_path = os.path.join(settings.MEDIA_ROOT, cv.thumbnail.name)
        #     if os.path.exists(old_thumbnail_path):
        #         os.remove(old_thumbnail_path)

        characters = string.ascii_letters + string.digits
        random_string = "".join(random.choice(characters) for _ in range(5))

        cv.generated_pdf.delete(save=False)  # Remove any in-memory reference
        cv.thumbnail.delete(save=False)  # Remove any in-memory reference

        # Save the new PDF to Django's storage
        pdf_filename = f"cv_{cv.id}_{random_string}.pdf"
        cv.generated_pdf.save(pdf_filename, ContentFile(pdf_data))

        # Generate thumbnail directly from the PDF data (using `convert_from_bytes`)
        images = convert_from_bytes(pdf_data, first_page=1, last_page=1)
        thumbnail_filename = f"thumbnail_{cv.id}_{random_string}.png"
        thumbnail_io = BytesIO()
        images[0].save(thumbnail_io, format="PNG")
        cv.thumbnail.save(thumbnail_filename, ContentFile(thumbnail_io.getvalue()))
        mycv = CV.objects.filter(id=cv.id).first()
        print("==============================================")
        print(mycv.thumbnail)
        print(mycv.generated_pdf)
        # if cv.generated_pdf and default_storage.exists(cv.generated_pdf.name):
        #     default_storage.delete(cv.generated_pdf.name)
        #
        # if cv.thumbnail and default_storage.exists(cv.thumbnail.name):
        #     default_storage.delete(cv.thumbnail.name)
    finally:
        if driver:
            driver.quit()