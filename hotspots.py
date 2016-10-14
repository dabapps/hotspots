from prettytable import PrettyTable
import click
import datetime
import iso8601
import math
import os
import requests


GITHUB_TOKEN = os.environ['GITHUB_TOKEN']
BASE_URL = 'https://api.github.com'


client = requests.Session()
client.auth = ('token', GITHUB_TOKEN)


def get_all_pages(url, params=None):
    all_results = []

    first_page = client.get(BASE_URL + url, params=params)
    all_results += first_page.json()

    if 'next' in first_page.links:
        url = first_page.links['next']['url']
        while True:
            page = client.get(url)
            all_results += page.json()
            if 'next' not in page.links:
                break
            url = page.links['next']['url']
    return all_results


def filter_bugfixes(prs):
    title_words = lambda pr: set(pr['title'].lower().split())
    bugfix_words = set(['bugfix', 'fix', 'bug', 'fixes', 'fixing'])
    is_bugfix = lambda pr: len(title_words(pr).intersection(bugfix_words)) > 0
    return [pr for pr in prs if is_bugfix(pr)]


def get_files(repo, pr):
    files_url = '/repos/' + repo + '/pulls/' + str(pr['number']) + '/files'
    results = get_all_pages(files_url)
    return results


def get_repository_creation_timestamp(repo):
    url = '/repos/' + repo
    response = client.get(BASE_URL + url)
    return iso8601.parse_date(response.json()['created_at'])


@click.command()
@click.argument('repo')
@click.option('--verbose', is_flag=True, default=False)
def main(repo, verbose):
    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)

    repository_created_at = get_repository_creation_timestamp(repo)
    repository_age_in_seconds = (now - repository_created_at).total_seconds()

    all_prs = get_all_pages('/repos/' + repo + '/pulls', params={'state': 'all', 'base': 'master'})
    bugfixes = filter_bugfixes(all_prs)
    click.echo("Found {} bugfix PRs\n".format(len(bugfixes)))

    scores = {}

    for bugfix in bugfixes:
        if verbose:
            click.echo("{} - {}".format(bugfix['created_at'], bugfix['title']))

        files = get_files(repo, bugfix)
        bugfix_created_at = iso8601.parse_date(bugfix['created_at'])
        bugfix_age_in_seconds = (now - bugfix_created_at).total_seconds()
        bugfix_age_as_a_proportion_of_repository_age = 1 - (bugfix_age_in_seconds / repository_age_in_seconds)

        # https://google-engtools.blogspot.co.uk/2011/12/bug-prediction-at-google.html
        score = 1 / (1 + math.exp((-12 * bugfix_age_as_a_proportion_of_repository_age) + 12))

        filenames = [f['filename'] for f in files if 'test' not in f['filename'] and 'migration' not in f['filename']]
        for filename in filenames:
            if filename not in scores:
                scores[filename] = 0
            scores[filename] += score

    top_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:10]
    table = PrettyTable()
    table.field_names = ['file', 'score']
    table.align = 'r'
    for name, score in top_scores:
        table.add_row([name, "{:.2f}".format(score)])
    click.echo(table.get_string())

if __name__ == "__main__":
    main()
