import os
import csv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import UnexpectedAlertPresentException
from selenium.common.exceptions import NoAlertPresentException
import time
import re


# Function to extract emails from text
def extract_emails_from_text(text):
    email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

    emails = re.findall(email_regex, text)
    
   # Define junk patterns in email addresses
    junk_patterns = [
        'wixpress',
        '.png', '.jpg', '.gif', 
        '@group.calendar.google.com',
        '.bet', 'info@', 'import.calendar.google.com', 'registration@', 'noreply', 'u003'
        # Add more patterns here as needed
    ]
    
    # Function to check if an email contains any junk pattern
    def is_junk(email):
        return any(junk_pattern in email for junk_pattern in junk_patterns)

    # Filter out junk emails
    valid_emails = [email for email in emails if not is_junk(email)]

    return valid_emails
    
# Function to find type of each school
def categorize_school_type(school_name):
    # Define keywords for each type of school
    
    keywords = {
        'Elementary': [r'\bes\b', r'\bel\b', r'elementary', r'grade school'],
        'Middle': [r'\bms\b', r'middle school', r'junior high'],
        'High': [r'\bhs\b', r'high school', r'high'],
    }

    # Use regular expression to split the school name into words and include possible punctuation
    words = school_name.lower()

    # Check if the school name contains any keyword for each type
    for school_type, key_list in keywords.items():
        for key in key_list:
            # Regular expression pattern to match the keyword as a whole word
            pattern = re.compile(key)
            if pattern.search(words):
                return school_type

    # If no type is determined, return 'Unknown' or a default type
    return 'Undetermined'
  


#Function to extract school names from csv file
def get_school_names_from_csv(csv_file, output_file):
    # Check if the CSV file exists
    if not os.path.isfile(csv_file):
        print("CSV file not found.")
        exit()

    # Check if the specified directory exists
    output_directory = os.path.dirname(output_file)
    if not os.path.exists(output_directory):
        print("The specified directory does not exist.")
        exit()

    # Extract the NCES District ID and State District ID from the CSV file
    state_district_ids = []

    with open(csv_file, 'r') as file:

        # Get the state name from the CSV file name
        state_name = os.path.splitext(os.path.basename(csv_file))[0]


        reader = csv.reader(file)


        # Find the cell containing the title "State District ID"
        state_cell_row = None
        state_cell_col = None

        for row_idx, row in enumerate(reader):
            for col_idx, cell in enumerate(row):
                if cell.strip() == "State District ID":
                    state_cell_row = row_idx
                    state_cell_col = col_idx
                    break
            if state_cell_row is not None:
                break


        # Check if the cell with the title is found
        if state_cell_row is None or state_cell_col is None:
            print("Unable to find the cell with the title 'State District ID'.")
            exit()

        # Read the rows and extract the IDs
        for row in reader:
            state_district_id = row[state_cell_col]

            # Skip rows with missing IDs
            if not state_district_id:
                continue

            state_district_ids.append(state_district_id)

    # Set up ChromeDriver options
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox") # This line is new


    driver = webdriver.Chrome(options=chrome_options)



    # Store the district and school names
    school_info_list = []

    
    # Process each district
    for i in range(len(state_district_ids)):
        state_district_id = state_district_ids[i]

        # Search for the school district name on the web using the IDs
        search_query = f"NCES {state_district_id}"
        driver.get(f"https://www.google.com/search?q={search_query}")

        print(f"Visiting URL: {driver.current_url}")

        # Extract the search results
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        search_results = soup.find_all('a')

        # Find and follow the link containing "District Detail" in the search results
        for result in search_results:
            if "District Detail" in result.text:
                district_detail_link = result['href']
                driver.get(district_detail_link)
                break

        # Find and follow the link matching the target format in the district detail page
        target_link = None
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        links = soup.find_all('a')
        for link in links:
            href = link.get('href')
            if href and "school_list.asp?Search=1&DistrictID=" in href:
                if href.startswith("../"):
                    href = href[3:]  # Remove the leading "../"
                target_link = urljoin("https://nces.ed.gov/ccd/", href)
                driver.get(target_link)
                break

        # Check if the target link was found
        if target_link is None:
            print("Target link not found.")
            continue

        # Extract the school names from the target link page
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        school_name_elements = soup.find_all('a', href=lambda href: href and 'school_detail.asp' in href)

        for element in school_name_elements:
            school_name = element.text.strip()
            school_type = categorize_school_type(school_name)  # Categorize the school
            school_info_list.append((school_name, school_type))  # Append as a tuple

        # Check for a "next" button and continue extracting school names from subsequent pages
        while True:
            next_button = soup.find('a', string='Next >>')
            if next_button:
                next_link = next_button['href']
                next_link = urljoin("https://nces.ed.gov/ccd/", next_link)
                next_link = next_link.replace("school_list.asp", "schoolsearch/school_list.asp")
                driver.get(next_link)
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                school_name_elements = soup.find_all('a', href=lambda href: href and 'school_detail.asp' in href)
                for element in school_name_elements:
                    school_name = element.text.strip()
                    school_type = categorize_school_type(school_name)  # Categorize the school
                    school_info_list.append((school_name, school_type))  # Append as a tuple
            else:
                break

    driver.quit()

    return school_info_list, state_name


# Function to lookup each school's faculty page
def lookup_faculty_pages_and_get_emails(state_name, school_info_list):
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox") 
    # Disable automatic downloads
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": "/dev/null",  # or "NUL" on Windows
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing_for_trusted_sources_enabled": False,
        "safebrowsing.enabled": False,
        "profile.default_content_setting_values.automatic_downloads": 1,
        "profile.default_content_settings.popups": 0
    })
    
    driver = webdriver.Chrome(options=chrome_options)

    school_emails = {}
    all_emails = set()
    
    for school_tuple in school_info_list:
        school_name, school_type = school_tuple
        search_query = f"Faculty page {school_name} {state_name}"
        time.sleep(5)

        try:
            driver.get(f"https://www.google.com/search?q={search_query}")
            print(f"Visiting URL: {driver.current_url}")

        except TimeoutException:
            print(f"Timeout occurred while trying to access Google search for {school_name}")
            continue  # Skip to the next iteration

        except UnexpectedAlertPresentException:
            try:
                alert = driver.switch_to.alert
                print(f"Alert detected: {alert.text}")
                alert.dismiss()  # or alert.accept()
            except NoAlertPresentException:
                print("No alert to dismiss")
            continue  # Skip to the next iteration

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        link_element = soup.find("div", {"class": "yuRUbf"})
        if link_element:
            anchor_tag = link_element.find("a")
            if anchor_tag:
                faculty_page_url = anchor_tag.get('href')
                try:
                    driver.get(faculty_page_url)
                   
                    emails_for_school = set(extract_emails_from_text(driver.page_source))
                    new_emails = emails_for_school - all_emails  # Emails in emails_for_school but not in all_emails
        
                    if new_emails:
                        school_emails[school_name, school_type] = new_emails
                        all_emails.update(new_emails) # Update the global set with the new unique emails

                        print(f"Added {len(new_emails)} new emails for {school_name}.")

                    else:
                        print(f"No new emails found for {school_name}.")

                except UnexpectedAlertPresentException:
                    alert = driver.switch_to.alert
                    print(f"Alert detected: {alert.text}")
                    alert.accept()  # or alert.dismiss()
                    continue  # Skip to the next loop iteration

                except Exception as e:
                    print(f"Error visiting {faculty_page_url}. Error: {e}")
                    continue  # Skip to the next loop iteration


    driver.quit()
    return school_emails, len(all_emails)


if __name__ == "__main__":
    start_time = time.time()
    
    csv_file = input("Please enter the path to the CSV file: ")
    output_file = input("Please enter the path and filename for the output text file: ")

    school_info_list, state_name = get_school_names_from_csv(csv_file, output_file)
    email_data, total_emails_found = lookup_faculty_pages_and_get_emails(state_name, school_info_list)

    with open(output_file, 'w') as file:
        file.write(f"State Name: {state_name}\n\n")

        for (school_name, school_type), emails in email_data.items():
            file.write(f"School Name: {school_name}\n")
            file.write(f"Type: {school_type}\n")  # Output the school type
            for email in emails:
                file.write(f"{email}\n")

            file.write("\n")

        file.write(f"Total Emails: {total_emails_found}")

    end_time = time.time()
    elapsed_time = end_time - start_time
    print(f"Process completed in {elapsed_time/60:.2f} minutes.")


