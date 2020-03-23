# REQUIREMENTS
# Have there's as environment variables
# export SLACK_VERIFICATION_TOKEN= <app verification token>
# export SLACK_TEAM_ID= <slack channel team id>
# export FLASK_APP= <app name>

# Google Sheets Imports
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import re

# Flask Imports
import requests
import os
from flask import abort, Flask, jsonify, request

# Zappa Imports
from zappa.asynchronous import task

# Authorization
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('client_creds.json', scope)
client = gspread.authorize(creds)

# SpreadSheet
sheet = client.open('UPE Candidate Tracker (LIVE)')
# Sheet Names
candSheet = sheet.worksheet("Candidate Tracker")
socialSheet = sheet.worksheet('Socials')
profSheet = sheet.worksheet('Professional Events')
onoSheet = sheet.worksheet('One-On-Ones')

# CANDIDATE TRACKER VALUES
standardCol = {
	'email': 1,
	'name': 2,
	'track': 3,
	'committee': 4
}
candSheetCol = {
    'socials_complete': 8,
    'socials_reqs': 11,
    'prof_complete': 9,
    'prof_reqs': 12,
    'ono_complete': 10,
    'ono_reqs': 13,
    'gm1': 19,
    'gm2': 20,
    'gm3': 21,
    'paid': 22,
    'challenge':24,
}

app = Flask(__name__)

"""
Checks whether provided action is a possible command
"""
def actionIsValid(action):
	return action in actions

"""
Checks whether payload matches correct verfication token and team ID
"""
def is_request_valid(request):
	is_token_valid = request.form['token'] == os.environ['SLACK_VERIFICATION_TOKEN']
	is_team_id_valid = request.form['team_id'] == os.environ['SLACK_TEAM_ID']

	return is_token_valid and is_team_id_valid

"""
Find the Google Sheet row of each name matching with expr
"""
def matchAllCandidates(expr):
	nameIndices = []
	nameLst = candSheet.col_values(standardCol['name'])[1:]

	for i in range(len(nameLst)):
		# expr matches candidate name
		if re.search(expr, nameLst[i]):
			nameIndices.append(i+2)

	return nameIndices

def getMatchedCandidates(expr):
	def getCandidateEvents(sheetName, jump):
		# Labels of current sheet
		sheetLabels = sheetName.row_values(1)
		# Candidate Info on current sheet
		candSheet = sheetName.row_values(candRow)

		eventsVisited = []
		for eventIndex in range(4, len(sheetLabels)-2, jump):
			if candSheet[eventIndex] and jump == 2:
				print(eventIndex)
				eventsVisited.append("{type} : {name}".format(type=candSheet[eventIndex], name=candSheet[eventIndex+1]))
			elif candSheet[eventIndex]:
				eventsVisited.append(sheetLabels[eventIndex])

		return eventsVisited


	candidates = {}

	# Locate rows of candidates matching with name
	matchedLst = matchAllCandidates(expr)

	# Retrieve respective information for every candidate
	for candRow in matchedLst:
		# Grab Candidate Infomation in `Candidate Tracker` Sheet
		candidate = candSheet.row_values(candRow)

		candInfo = {}

		# Insert `Candidate Tracker` contents into dictionary 
		for col, colNum in candSheetCol.items():
			candInfo[col] = candidate[colNum-1]

		# Insert `Socials` contents into dictionary
		candInfo['socials'] = getCandidateEvents(socialSheet, 1)
		# Insert `Professional Events` contents into dictionary
		candInfo['prof'] = getCandidateEvents(profSheet, 1)
		# Insert `One-on-Ones` contents into dictionary
		candInfo['onos'] = getCandidateEvents(onoSheet, 2)



		candidates[candidate[standardCol['name'] - 1]] = candInfo 
		
	return candidates

# {
# 	'socials_complete': '1', 
# 	'socials_reqs': '2', 
# 	'prof_complete': '2', 
# 	'prof_reqs': '2', 
# 	'ono_complete': '2', 
# 	'ono_reqs': '2', 
# 	'socials': ['Big/Little Mixer 2/15'], 
# 	'prof': ['Jane Street (2/26)']
# }


def formatCandidateText(dct):
	block = []
	# Format each candidate into markdown format
	for name in dct.keys():
		# Grab candidate contents
		candInfo  = dct[name]

		nameTxt = '*{name}*\n'.format(name=name)

		# Socials
		socialsTxt = '• Socials: {pss}/{req}\n'.format(pss=candInfo['socials_complete'], req=candInfo['socials_reqs'])
		for social in candInfo['socials']:
			socialsTxt += '\t - {social}\n'.format(social=social)

		# Professional
		profTxt = '• Professional: {pss}/{req}\n'.format(pss=candInfo['prof_complete'], req=candInfo['prof_reqs'])
		for prof in candInfo['prof']:
			profTxt += '\t - {prof}\n'.format(prof=prof)

		# One-on-Ones
		onoTxt = '• One-on-One: {pss}/{req}\n'.format(pss=candInfo['ono_complete'], req=candInfo['ono_reqs'])
		for ono in candInfo['onos']:
			onoTxt += '\t - {ono}\n'.format(ono=ono)

		# Challenge
		challengeTxt = '• Challenge: {done}\n'.format(done='Done' if candInfo['challenge']=='YES' else '*NO*')

		# General Meeting
		gm1 = '• GM1 Requirements: {done}\n'.format(done='Yes' if candInfo['gm1']=='YES' else '*NO*')
		gm2 = '• GM2 Requirements: {done}\n'.format(done='Yes' if candInfo['gm2']=='YES' else '*NO*')
		gm3 = '• GM3 Requirements: {done}\n'.format(done='Yes' if candInfo['gm3']=='YES' else '*NO*')
		paid = '• Paid: {done}\n'.format(done='Yes' if candInfo['paid']=='TRUE' else '*NO*')

		requirements = {
			'type':'section', 
			'text': {
				'type': 'mrkdwn',
				'text': nameTxt + socialsTxt + profTxt + onoTxt + challengeTxt
			}
		}

		attendance = {
			'type':'section', 
			'text': {
				'type': 'mrkdwn',
				'text': gm1 + gm2 + gm3 + paid
			}
		}

		block.append(requirements)
		block.append(attendance)

		# Push divider
		block.append({"type" : "divider"})

	return block

def error(msg, attachments, response_url):
	data = {
		"response_type": "ephemeral",
    	"text": msg,
    	"attachments": attachments
	}
	requests.post(response_url, json=data)

# Possible actions
actions = {
	'/check' : {
		'helpTxt' : [{'text': "Type `/check <candidate name>` to view a candidate's status"}],
	}
}

@task
def runGoogleSheets(req):
	response_url = req['response_url']

	# Check if argument len is sufficient
	if len(req['text']) < 3:
		error('Please submit an expression with more than two characters', actions['/check']['helpTxt'], req['response_url'])
		return

	# Retrieve candidate info according to text in Slack payload
	candidateInfos = getMatchedCandidates(req['text'])

	if len(candidateInfos) == 0:
		error('No candidates found with given keyword', actions['/check']['helpTxt'], req['response_url'])
		return

	# Format candidate info into Slack JSON format
	candidateFormatString = formatCandidateText(candidateInfos)

	data = {
		'response_type': 'ephemeral',
		'blocks' : candidateFormatString,
	}
	requests.post(response_url, json=data)

@app.route('/check', methods=['POST'])
def track_candidates():

	# Check if valid request through (team_id) and (token)
	if not is_request_valid(request):
		abort(400)

	# Retrieve payload from Slack
	req = request.form

	# Check if possible command
	if not actionIsValid(req['command']):
		error('Please submit a valid command', actions['/check']['helpTxt'], req['response_url'])
		return

	runGoogleSheets(req)

	return jsonify(
		response_type='ephemeral',
		text='Loading your candidate data...',
	)

if __name__ == '__main__':
    app.run()