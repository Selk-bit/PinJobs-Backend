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
from .models import Job, JobSearch, Notification
from django.core.files.storage import default_storage
from paypalcheckoutsdk.core import PayPalHttpClient, SandboxEnvironment
from bs4 import BeautifulSoup
import re
import asyncio
import aiohttp
from datetime import datetime
import requests
from fake_useragent import UserAgent
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

ua = UserAgent()
client_id = os.getenv('PAYPAL_CLIENT_ID')
client_secret = os.getenv('PAYPAL_CLIENT_SECRET')
environment = SandboxEnvironment(client_id=client_id, client_secret=client_secret)
paypal_client = PayPalHttpClient(environment)
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
    folder = 'chromedriver/'
    chrome_options = Options()
    width = random.randint(1000, 2000)
    height = random.randint(500, 1000)
    chrome_options.add_argument(f"window-size={width},{height}")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.125 Safari/537.36")
    # chrome_options.add_argument("--headless")
    # chrome_options.add_argument('--no-sandbox')
    # chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument("disable-infobars")
    chrome_options.add_argument('log-level=3')
    # chrome_options.binary_location = os.getenv("CHROME_BIN", "/opt/google/chrome/google-chrome")
    # chrome_options.binary_location = "/opt/render/chromium/chrome-linux/chrome"
    return chrome_options


def construct_url(keyword, location):
    keyword_encoded = urllib.parse.quote(keyword)
    location_encoded = urllib.parse.quote(location)
    url = f"https://www.linkedin.com/jobs/search?keywords={keyword_encoded}&location={location_encoded}&position=1&pageNum=0"
    return url


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

    1. **Location Match (20 points):**
       - **20 points:** Candidate's city matches the job location or the job is remote.
       - **15 points:** Candidate's city is within the same region or state as the job.
       - **10 points:** Candidate's city is within the same country.
       - **5 points:** Candidate is willing to relocate or the job allows for relocation.
       - **0 points:** Locations are different with no indication of relocation.

    2. **Experience Match (20 points):**
       - Calculate the percentage of required experience met by the candidate.
       - **Points Awarded:** (Candidate's Years of Experience / Required Experience) * 20
       - If the candidate exceeds the required experience, cap the score at 20 points.

    3. **Skills Match (30 points):**
       - Compare the required skills with the candidate's skills.
       - **Points Awarded:** (Number of Matching Skills / Total Required Skills) * 30
       - Include both hard and soft skills in the assessment.

    4. **Education Match (10 points):**
       - **10 points:** Candidate's education level exceeds the requirement.
       - **8 points:** Candidate's education level meets the requirement.
       - **5 points:** Candidate's education is slightly below the requirement.
       - **0 points:** Candidate's education does not meet the requirement.

    5. **Role Requirements Match (10 points):**
       - Assess the relevance of the candidate's past responsibilities to the job's responsibilities.
       - **Points Awarded:** (Relevance Percentage) * 10
       - Use detailed analysis to determine relevance.

    6. **Language Proficiency (5 points):**
       - **5 points:** Candidate fully meets language requirements.
       - **2-4 points:** Candidate partially meets language requirements.
       - **0 points:** Candidate does not meet language requirements.

    7. **Additional Criteria (5 points):**
       - Consider certifications, interests, and other relevant factors.
       - **Points Awarded:** (Relevance Percentage) * 5

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


def scrape_jobs(cv_data, candidate_data, num_jobs_to_scrape):
    # Read candidate profile
    candidate_profile = candidate_data
    candidate = candidate_profile['candidate']
    partial_jobs_collected = []
    total_jobs_collected = []
    anchors_processed = set()

    # Extract keyword and location from candidate profile
    keyword = candidate_profile['title']
    location = candidate_profile['city']

    # Construct the search URL
    multiple_jobs_url = construct_url(keyword, location)

    # Headers for the HTTP requests
    multiple_jobs_headers = {
        "User-Agent": f"Mozilla/5.0 (Windows NT {random.randint(6, 10)}.{random.randint(0, 3)}; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(80, 95)}.0.{random.randint(3000, 4000)}.{random.randint(100, 150)} Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Cookie": 'lang=v=2&lang=en-us; bcookie="v=2&13690459-2695-4db8-8920-eb8acafd8bb0"; lidc="b=OGST01:s=O:r=O:a=O:p=O:g=3446:u=1:x=1:i=1731604780:t=1731691180:v=2:sig=AQH9Fke10UQG9Y2cVZtB9GxcuhLRjHYT"; __cf_bm=t1G.2BT5aBYyrtSdXb1i1P1C62LySBfwfGB0qPAeJKM-1731604780-1.0.1.1-vsyEyIXbZoIk2K9ZdnwsX_JX50i.PWUOGpCco0p_8YN4Ox9urlWJdFzhWVcmSx2mMfquMeUrLfJB4OmWaplE_g; JSESSIONID=ajax:7418003674519976640; bscookie="v=1&20241114171953262036d0-c9e0-4821-8104-95261fbea1f2AQGQhsqDVF82rmiyryMBtG9R_9mqrteN"; AMCVS_14215E3D5995C57C0A495C55%40AdobeOrg=1; AMCV_14215E3D5995C57C0A495C55%40AdobeOrg=-637568504%7CMCIDTS%7C20042%7CMCMID%7C24006825359064228502848929369249235580%7CMCAAMLH-1732209601%7C6%7CMCAAMB-1732209601%7C6G1ynYcLPuiQxYZrsz_pkqfLG9yMXBpb2zX5dvJdYQJzPXImdj0y%7CMCOPTOUT-1731612001s%7CNONE%7CvVersion%7C5.1.1; aam_uuid=24229005248847717212830020980619194807; _gcl_au=1.1.1528757662.1731604801; ccookie=0001AQGJ9Xfxg73P4wAAAZMrsWe4+zApGcXdE5zp5BKFyMPBrHTrMd+HPwNATFZpf3K6yYhWGy2cxQN+vft6FExugPGJMfXh49ZkQd/J9FOALHHAvt1wIQ3G5zTTqlpL6u+YtBHNSdhX62lCOcKPgISJ2Jsn3ifKnxsiOANIowr213txeQ==; _uetsid=ae1cad00a2ac11ef941fe55ffdabcbc5; _uetvid=ae1cc490a2ac11efa8cd6b2dc3fdb04a',
        "Upgrade-Insecure-Requests": "1"
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

    existing_job_searches = JobSearch.objects.filter(candidate=candidate)
    already_scraped_urls = [job_search.job.original_url for job_search in existing_job_searches]

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

    # Calculate start values for pagination
    start_values = list(range(25, total_jobs, 25))

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
    process_job_listings(soup)

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
                    "Accept": multiple_jobs_headers["Accept"],
                    "Cookie": 'lang=v=2&lang=en-us;',
                    "Upgrade-Insecure-Requests": "1"
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
        # Extract job ID from the original job URL
        job_id_match = re.search(r'-(\d+)\?', job['url'])
        if job_id_match:
            job_id = job_id_match.group(1)
        else:
            print(f"Failed to extract job ID from URL: {job['url']}")
            return

        # Construct the new job detail URL
        job_detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

        job_detail_text = await fetch_job_detail(session, job_detail_url, "top-card-layout__title", 100)
        if job_detail_text:
            # Parse the job detail page
            soup = BeautifulSoup(job_detail_text, 'html.parser')
            # Extract required data
            # Title
            title_tag = soup.find('h2', class_='top-card-layout__title')
            title = title_tag.get_text(strip=True) if title_tag else None
            # Company name
            company_tag = soup.find('a', class_=re.compile('topcard__org-name-link'))
            company_name = company_tag.get_text(strip=True) if company_tag else None
            # Location
            location_tag = soup.find('span', class_='topcard__flavor topcard__flavor--bullet')
            location = location_tag.get_text(strip=True) if location_tag else None
            # Salary (leave empty)
            salary = None
            # Description
            description_parts = []
            description_tag = soup.find('div', class_='description__text description__text--rich')
            if description_tag:
                text = description_tag.get_text(separator='\n', strip=True)
                text = text.replace('Show more', '').replace('Show less', '').strip()
                description_parts.append(text)
            criteria_tag = soup.find('div', class_='description__job-criteria-list')
            if criteria_tag:
                text = criteria_tag.get_text(separator='\n', strip=True)
                text = text.replace('Show more', '').replace('Show less', '').strip()
                description_parts.append(text)
            description = '\n'.join(description_parts) if description_parts else None
            # Collect data
            job['title'] = title
            job['company_name'] = company_name
            job['location'] = location
            job['salary_range'] = salary
            job['description'] = description
            job['original_url'] = job['url']
            # job['posted_date'] is already set from earlier
            partial_jobs_collected.append(job)
            total_jobs_collected.append(job)

            print(f"Title: {title}")
            print(f"Company: {company_name}")
            print(f"Location: {location}")
            print(f"Salary: {salary}")
            print(f"Description: {description}")
            print(f"Posted Date: {job['date'] if job['date'] else 'N/A'}")
            print(f"Job URL: {job['url']}")
            print("-" * 80)
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

    # Process jobs in batches and send to Gemini
    batch_size = 5
    for i in range(0, len(partial_jobs_collected), batch_size):
        jobs_batch = partial_jobs_collected[i:i+batch_size]
        prompt = construct_prompt(cv_data, jobs_batch)
        gemini_response = get_gemini_response(prompt)
        if "```" in gemini_response:
            gemini_response = (gemini_response.split("```json")[-1]).split("```")[0]
        try:
            jobs_with_scores = json.loads(gemini_response)
            print("Gemini Response:")
            print(json.dumps(jobs_with_scores, indent=4, ensure_ascii=False))
            # Create jobs and job searches in the database
            for job_data in jobs_with_scores:
                # Normalize the job URL to remove query parameters
                job_url_no_query = job_data['original_url'].split("?")[0]

                # Check if the job already exists
                existing_job = Job.objects.filter(original_url=job_url_no_query).first()

                if existing_job:
                    # Check if a JobSearch exists for the authenticated candidate and the existing job
                    if not JobSearch.objects.filter(candidate=candidate, job=existing_job).exists():
                        # Create a JobSearch for the existing job
                        JobSearch.objects.create(
                            candidate=candidate,
                            job=existing_job,
                            similarity_score=job_data['score']
                        )
                        candidate.credits -= 1  # Deduct one credit for creating the JobSearch
                        candidate.save()
                    else:
                        print(f"JobSearch already exists for candidate and job: {job_url_no_query}")
                else:
                    # Create a new job if it doesn't exist
                    job = Job.objects.create(
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
                        posted_date=job_data.get('posted_date')
                    )

                    # Create a JobSearch for this candidate and job
                    JobSearch.objects.create(
                        candidate=candidate,
                        job=job,
                        similarity_score=job_data['score']
                    )
                    candidate.credits -= 1  # Deduct one credit for creating the JobSearch
                    candidate.save()
                # notification = Notification.objects.create(
                #     candidate=candidate,
                #     job=job,
                #     message=f"A new job '{job.title}' at {job.company_name} has been added to your job search."
                # )
                #
                # # Send notification to WebSocket
                # channel_layer = get_channel_layer()
                # async_to_sync(channel_layer.group_send)(
                #     f"notifications_{candidate.user.id}",
                #     {
                #         "type": "send_notification",
                #         "message": notification.message
                #     }
                # )

        except json.JSONDecodeError as e:
            print(f"Error parsing Gemini response: {e}")
            print("Gemini response was:")
            print(gemini_response)

    print("Scraping completed successfully.")