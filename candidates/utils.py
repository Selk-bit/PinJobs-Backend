import os
import google.generativeai as genai
from django.conf import settings
import random
import platform
import json
import time
from selenium.common.exceptions import NoSuchElementException, WebDriverException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium import webdriver
import undetected_chromedriver as uc
import chromedriver_autoinstaller
import urllib.parse
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import psutil
import shutil
from .constants import *
from .models import Job, JobSearch
from django.core.files.storage import default_storage
from paypalcheckoutsdk.core import PayPalHttpClient, SandboxEnvironment

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
    chrome_options.add_argument("--headless")
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_argument("disable-infobars")
    chrome_options.add_argument('log-level=3')
    chrome_options.binary_location = os.getenv("CHROME_BIN", "/opt/google/chrome/google-chrome")
    # chrome_options.binary_location = f"{default_storage.open(f"{folder}chromedriver.exe")}"
    return chrome_options


def construct_url(keyword, location):
    keyword_encoded = urllib.parse.quote(keyword)
    location_encoded = urllib.parse.quote(location)
    url = f"https://www.linkedin.com/jobs/search?keywords={keyword_encoded}&location={location_encoded}&position=1&pageNum=0&f_TPR=r2592000"
    return url


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
        "requirements": "list of strings (try extracting requirements from the description if they're not clearly listed)",
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
    # Read candidate profile from candidate.json
    candidate_profile = candidate_data
    candidate = candidate_profile['candidate']
    partial_jobs_collected = []
    total_jobs_collected = []
    anchors_processed = set()
    while True:  # Loop infinitely until the job is done
        driver = None  # Initialize driver to None at the start of each loop
        try:
            keyword = candidate_profile['title']
            location = candidate_profile['city']
            url = construct_url(keyword, location)
            chrome_options = get_options()
            # version_main = int(chromedriver_autoinstaller.get_chrome_version().split(".")[0])
            # driver = uc.Chrome(options=chrome_options, version_main=version_main)
            folder = 'chromedriver/'
            # service = Service(executable_path=f"{default_storage.open(f"{folder}chromedriver.exe")}")
            if os.path.isdir("./chromedriver/"):
                # Iterate over each item in the folder
                for file_name in os.listdir("./chromedriver/"):
                    # Only print if it's a file (not a directory)
                    if os.path.isfile(os.path.join("./chromedriver/", file_name)):
                        print(file_name)
            service = Service(executable_path=os.path.join(os.getenv("HOME"), "bin", "chromedriver"))
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.maximize_window()
            # Visit a random popular website instead of Google
            initial_site = random.choice(POPULAR_WEBSITES)
            driver.get(initial_site)
            time.sleep(random.uniform(1, 3))

            while True:
                existing_job_searches = JobSearch.objects.filter(candidate=candidate)
                already_scraped_urls = [job_search.job.original_url for job_search in existing_job_searches]
                try:
                    driver.get(url)
                    print(f"Visiting URL: {url}")
                    time.sleep(random.uniform(1, 3))  # Give time for the page to load
                except (WebDriverException, TimeoutException) as e:
                    print(f"Connection error: {e}")
                    raise Exception("Connection error encountered, restarting...")

                # Check if we are redirected to the home page
                if check_exists_by_xpath(driver, JOB_RESULTS_XPATH):
                    break  # Exit the loop if SIGN_IN_BUTTON_XPATH is not found
                # If SIGN_IN_BUTTON_XPATH is found, visit 2-3 random websites
                num_sites = random.randint(2, 3)
                for _ in range(num_sites):
                    random_site = random.choice(POPULAR_WEBSITES)
                    driver.get(random_site)
                    time.sleep(random.uniform(1, 3))

            if check_exists_by_xpath(driver, MODAL_DISMISS_XPATH):
                print("Remove Modal")
                click_forcefully(driver, driver.find_element(By.XPATH, MODAL_DISMISS_XPATH), True, "//body")

            move_result = move_until_found(driver, ANCHORS_XPATH, 100)
            if move_result == 'sign_in':
                print("Sign-in detected during move_until_found, visiting random sites.")
                num_sites = random.randint(2, 3)
                for _ in range(num_sites):
                    random_site = random.choice(POPULAR_WEBSITES)
                    driver.get(random_site)
                    time.sleep(random.uniform(1, 3))
                continue  # Restart the scraping loop

            previous_anchor = None

            while len(total_jobs_collected) < num_jobs_to_scrape:
                anchors = driver.find_elements(By.XPATH, ANCHORS_XPATH)
                anchors_to_process = []

                for anchor in anchors:
                    job_link = anchor.get_attribute('href')
                    if job_link and job_link not in anchors_processed and (job_link.split("?")[0]).strip() not in already_scraped_urls:
                        anchors_processed.add(job_link)
                        anchors_to_process.append(anchor)

                if not anchors_to_process:
                    # Scroll to load more jobs
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(random.uniform(1, 2))
                    # Check if new anchors are loaded
                    new_anchors = driver.find_elements(By.XPATH, ANCHORS_XPATH)
                    if len(new_anchors) == len(anchors):
                        # No new anchors loaded, break
                        break
                    else:
                        continue  # Continue to process new anchors

                for anchor in anchors_to_process:
                    if len(total_jobs_collected) >= num_jobs_to_scrape:
                        break
                    parent_elem = anchor.find_element(By.XPATH, "..")
                    driver.execute_script("arguments[0].scrollIntoView();", anchor)
                    time.sleep(random.uniform(0.5, 1.5))  # Give time for new jobs to load
                    job_title_xpath = f"//h2[contains(text(), '{(anchor.text).split()[0].strip()}')]"
                    move_result = move_until_found(driver, job_title_xpath, 100, TITLE_XPATH, anchor, previous_anchor)
                    if move_result == 'sign_in':
                        print("Sign-in detected during job scraping, visiting random sites.")
                        num_sites = random.randint(2, 3)
                        for _ in range(num_sites):
                            random_site = random.choice(POPULAR_WEBSITES)
                            driver.get(random_site)
                            time.sleep(random.uniform(1, 3))
                        break  # Break out to restart the scraping loop
                    previous_anchor = anchor
                    click_forcefully(driver, anchor, True, TITLE_XPATH)
                    title = anchor.text.strip()
                    company = get_company(parent_elem, COMPANY_XPATH)
                    location_city = get_location(driver, LOCATION_XPATH)
                    salary = get_salary(driver, SALARY_XPATH)
                    description = get_description(driver, DESCRIPTION_XPATH)
                    posted_date = get_date(parent_elem, POST_DATE_XPATH)
                    job_link = anchor.get_attribute('href')

                    job_data = {
                        "title": title,
                        "company_name": company,
                        "location": location_city,
                        "salary_range": salary,
                        "posted_date": posted_date,
                        "description": description,
                        "original_url": job_link
                    }
                    partial_jobs_collected.append(job_data)
                    total_jobs_collected.append(job_data)

                    print(f"Link: {job_link}")
                    print(f"Title: {title}")
                    print(f"Company: {company}")
                    print(f"Location: {location_city}")
                    print(f"Salary: {salary}")
                    print(f"Description: {description}")
                    print(f"Date: {posted_date}")
                    print("=====================================================================")
                    time.sleep(random.uniform(1, 3))

                    # Send data to Gemini when we have a batch of up to 5 jobs or when we've reached the total number
                    if len(partial_jobs_collected) % 5 == 0 or len(total_jobs_collected) == num_jobs_to_scrape:
                        prompt = construct_prompt(cv_data, partial_jobs_collected)
                        gemini_response = get_gemini_response(prompt)
                        if "```" in gemini_response:
                            gemini_response = (gemini_response.split("```json")[-1]).split("```")[0]
                        try:
                            jobs_with_scores = json.loads(gemini_response)
                            print("Gemini Response:")
                            print(json.dumps(jobs_with_scores, indent=4, ensure_ascii=False))
                            # Create jobs and job searches in the database
                            for job_data in jobs_with_scores:
                                job = Job.objects.create(
                                    title=job_data['title'],
                                    description=job_data['description'],
                                    company_name=job_data['company_name'],
                                    location=job_data['location'],
                                    salary_range=job_data.get('salary_range'),
                                    min_salary=job_data.get('min_salary'),
                                    max_salary=job_data.get('max_salary'),
                                    employment_type=job_data.get('employment_type', 'full-time'),
                                    original_url=job_data['original_url'].split("?")[0],
                                    skills_required=job_data['skills_required'],
                                    requirements=job_data['requirements'],
                                    benefits=job_data['benefits'],
                                    posted_date=job_data.get('posted_date')
                                )

                                # Create a JobSearch for this candidate and job
                                JobSearch.objects.create(
                                    candidate=candidate_profile['candidate'],
                                    job=job,
                                    similarity_score=job_data['score']
                                )
                                candidate.credits -= 1
                                candidate.save()
                        except json.JSONDecodeError as e:
                            print(f"Error parsing Gemini response: {e}")
                            print("Gemini response was:")
                            print(gemini_response)
                        # Reset jobs_collected for the next batch
                        partial_jobs_collected = []

                if len(total_jobs_collected) >= num_jobs_to_scrape:
                    break

                # Scroll to load more jobs
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(random.uniform(1, 2))

            time.sleep(10)
            kill_chrome(driver)
            break  # Break the infinite loop after successful execution
        except FileNotFoundError as e:
            print(f"Error: {e}")
            break
        except WebDriverException as e:
            print(f"WebDriver error: {e}")
            break
        except Exception as e:
            print(f"An error occurred: {e}")
            if driver:
                kill_chrome(driver)
            print("Restarting the scraping process...")
            continue  # Start over again
