import re
import urlparse
from time import sleep
from calaccess_processed.management.commands import ScrapeCommand
from calaccess_processed.models.scraped import ScrapedElection, ScrapedCandidate

class Command(ScrapeCommand):
    """
    Scraper to get the list of candidates per election.
    """
    help = "Scrape links between filers and elections from CAL-ACCESS site"

    def build_results(self):
        self.header("Scraping election candidates")

        soup = self.get_html('/Campaign/Candidates/list.aspx?view=certified&electNav=93')

        # Get all the links out
        links = soup.findAll('a', href=re.compile(r'^.*&electNav=\d+'))

        # Drop the link that says "prior elections" because it's a duplicate
        links = [
            l for l in links
            if l.find_next_sibling('span').text != 'Prior Elections'
        ]

        # Loop through the links
        results = []
        for i, link in enumerate(links):
            # Get each page and its data
            url = urlparse.urljoin(self.base_url, link["href"])
            data = self.scrape_page(url)
            # Add the name of the election
            data['election_name'] = link.find_next_sibling('span').text.strip()
            data['election_year'] = int(data['election_name'][:4])
            # The index value is used to preserve sorting of elections,
            # since multiple elections may occur in a year.
            # BeautifulSoup goes from top to bottom,
            # but the top most election is the most recent so it should
            # have the highest id.
            data['sort_index'] = len(links) - i
            # Add it to the list
            results.append(data)
            # Take a rest
            sleep(0.5)

        return results

    def scrape_page(self, url):
        """
        Pull the elections and candidates from a CAL-ACCESS page.
        """
        # Go and get the page
        soup = self.get_html(url)

        races = {}
        # Loop through all the election sets on the page
        for section in soup.findAll('a', {'name': re.compile(r'[a-z]+')}):

            # Check that this data matches the structure we expect.
            section_name_el = section.find('span', {'class': 'hdr14'})

            # If it doesn't, skip this one
            if not section_name_el:
                continue

            # Loop thorugh all the rows in the section table
            for office in section.findAll('td'):

                # Check that this data matches the structure we expect.
                title_el = office.find('span', {'class': 'hdr13'})

                # If it doesn't, skip
                if not title_el:
                    continue

                office_name = title_el.text

                # Log what we're up to
                if self.verbosity > 2:
                    self.log(' Scraping office %s' % office_name)

                # Pull the candidates out
                candidates = []
                for c in office.findAll('a', {'class': 'sublink2'}):
                    candidates.append({
                        'name': c.text,
                        'scraped_id': re.match(r'.+id=(\d+)', c['href']).group(1)
                    })

                for c in office.findAll('span', {'class': 'txt7'}):
                    candidates.append({
                        'name': c.text,
                        'scraped_id':  ''
                    })

                # Add it to the data dictionary
                races[office_name] = candidates

        return {
            'election_id': int(re.match(r'.+electNav=(\d+)', url).group(1)),
            'races': races,
        }

    def process_results(self, results):
        """
        Process the scraped data.
        """
        self.log(' Processing %s elections.' % len(results))

        # Loop through all the results
        for election_data in results:

            self.log(' Processing %s' % election_data['election_name'])

            election, c = ScrapedElection.objects.get_or_create(
                name = election_data['election_name'],
                year = election_data['election_year'],
                election_id = election_data['election_id'],
                sort_index = election_data['sort_index'],
            )

            if c and self.verbosity > 2:
                self.log(' Created %s' % election)
            
            # Loop through each of the races
            for office_name, candidates in election_data['races'].items():

                # Loop through each of the candidates
                for candidate_data in candidates:
                    # Add the office information to the candidate dict
                    candidate_data['office_name'] = office_name
                    # Create the candidate object
                    candidate, c = ScrapedCandidate.objects.get_or_create(**candidate_data)
                    
                    if c:
                        # Associate with the election object
                        candidate.election = election
                        candidate.save()
                        if self.verbosity > 2:
                            self.log(' Created %s' % candidate)
