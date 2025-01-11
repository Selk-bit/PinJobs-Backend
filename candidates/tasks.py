from celery import shared_task
from django.utils import timezone
from .models import Candidate, CV, CVData, ScrapingSetting, KeywordLocationCombination
from .utils import scrape_jobs
from datetime import timedelta
from django.forms.models import model_to_dict


@shared_task
def scheduled_job_scraping():
    candidates = Candidate.objects.filter(is_scraping=False)

    for candidate in candidates:
        time_now = timezone.now()
        last_scrape = candidate.last_scrape_time or timezone.now() - timedelta(days=1)

        # Determine the next scrape time based on the interval and unit
        if candidate.scrape_unit == 'hours':
            next_scrape = last_scrape + timedelta(hours=candidate.scrape_interval)
        elif candidate.scrape_unit == 'days':
            next_scrape = last_scrape + timedelta(days=candidate.scrape_interval)
        elif candidate.scrape_unit == 'weeks':
            next_scrape = last_scrape + timedelta(weeks=candidate.scrape_interval)

        # If it's time to run the scraping task
        if time_now >= next_scrape:
            run_scraping_task(candidate_id=candidate.id)


def get_cv_data(candidate):
    try:
        # Get the CV object related to the candidate and then get the CVData
        cv = CV.objects.get(candidate=candidate)
        cv_data = CVData.objects.get(cv=cv)

        # Convert CVData model to a dictionary
        cv_data_dict = model_to_dict(cv_data)

        # Assuming some fields need to be parsed from JSONField, e.g., work, skills, etc.
        # If they are stored as JSON, they can be passed directly
        # If they require any other processing, do it here
        cv_data_dict['work'] = cv_data.work if cv_data.work else []
        cv_data_dict['educations'] = cv_data.educations if cv_data.educations else []
        cv_data_dict['languages'] = cv_data.languages if cv_data.languages else []
        cv_data_dict['skills'] = cv_data.skills if cv_data.skills else []
        cv_data_dict['interests'] = cv_data.interests if cv_data.interests else []
        cv_data_dict['social'] = cv_data.social if cv_data.social else []
        cv_data_dict['certifications'] = cv_data.certifications if cv_data.certifications else []
        cv_data_dict['projects'] = cv_data.projects if cv_data.projects else []
        cv_data_dict['volunteering'] = cv_data.volunteering if cv_data.volunteering else []
        cv_data_dict['references'] = cv_data.references if cv_data.references else []

        return cv_data_dict

    except CV.DoesNotExist:
        return {}
    except CVData.DoesNotExist:
        return {}


@shared_task
def run_scraping_task():

    settings = ScrapingSetting.objects.first()
    if settings.is_scraping:
        print("Scraping task already running. Exiting.")
        return

    settings.is_scraping = True
    settings.save()

    try:
        num_jobs_to_scrape = settings.num_jobs_to_scrape
        total_jobs_scraped = 0

        # Fetch unscripted combinations
        combinations = KeywordLocationCombination.objects.filter(is_scraped=False)

        for combination in combinations:

            keyword = combination.keyword.keyword
            location = combination.location.location

            jobs_collected = scrape_jobs(keyword, location, num_jobs_to_scrape - total_jobs_scraped)
            total_jobs_scraped += len(jobs_collected)

            # Mark the combination as scraped if all jobs fetched
            if not jobs_collected or len(jobs_collected) < num_jobs_to_scrape:
                combination.is_scraped = True
                combination.save()

            if total_jobs_scraped >= num_jobs_to_scrape:
                break

    except Exception as e:
        print(f"Error during scraping task: {e}")
    finally:
        # Ensure the is_scraping flag is reset
        settings.is_scraping = False
        settings.save()