import json
import pickle
import sys
import traceback
from datetime import datetime

from monkeylearn import MonkeyLearn
from slacker import Slacker
from slackclient import SlackClient

from create_modules import create_module_user


crontable = []
outputs = []

historical_convs = {}
current_convs = {}

# These will be initialized in setup function
config = {}
ml = None
slack = None
sc = None
DEBUG = False
user_names = {}
channel_names = {}
module_ids = {}


def is_in_conversation(message, conv):
    if len(conv['messages']) == 0:
        return True
    return (message['ts'] - conv['messages'][-1]['ts']).total_seconds() <= config['MESSAGE_DISTANCE']


def create_conversation(start, messages=[], text='', authors=set([])):
    return {'start': start, 'messages': messages, 'text': text, 'authors': authors, 'alerted': set([])}


def get_user_name(user_id):
    return user_names[user_id]


def get_channel_name(channel_id):
    return channel_names[channel_id]


def setup(plugin_config):
    print 'Setting up MonkeyBot...'
    print plugin_config

    global config
    global ml
    global slack
    global sc
    global DEBUG
    global user_names
    global channel_names
    global module_ids

    config = plugin_config
    ml = MonkeyLearn(config['MONKEYLEARN_TOKEN'])
    slack = Slacker(config['SLACK_API_TOKEN'])
    sc = SlackClient(config['SLACK_BOT_TOKEN'])
    DEBUG = config['DEBUG']

    # Get users list
    response = slack.users.list()
    users = response.body['members']
    for user in users:
        user_names[user['id']] = user['name']

    # Get channel list
    response = slack.channels.list()
    channels = response.body['channels']
    for channel in channels:
        channel_names[channel['id']] = channel['name']

    try:
        f2 = open('user_modules.pickle', 'rb')
        module_ids = pickle.load(f2)
        f2.close()
    except:
        module_ids = {}

    print '\n----- REGISTERED USERS -----'
    print module_ids.keys()


def process_message(data):

    if DEBUG:
        print '\n----- RAW DATA -----'
        print datetime.now()
        print data

    try:
        if 'subtype' not in data:
            if data['channel'].startswith('D'):
                # direct message
                # process command here

                user = get_user_name(data['user'])
                message = {
                    'ts': datetime.fromtimestamp(float(data['ts'])),
                    'text': data['text'],
                    'user': user
                }

                command = message['text'].split()[0]
                args_list = message['text'].split()[1:]

                if command == '\create':

                    if len(args_list) > 0:
                        user = args_list[0]

                    if user in module_ids.keys():
                        outputs.append([data['channel'], 'You are already registered!'])
                        return

                    if len(module_ids.keys()) >= config['MAX_USERS']:
                        outputs.append([data['channel'], 'Sorry, no more room for new users...'])
                        return

                    try:
                        f = open('plugins/monkeybot/users_data/training_set_' + user + '.csv')
                    except:
                        outputs.append([data['channel'], 'Sorry, no history about ' + user + '...'])
                        return

                    sc.api_call(
                        "chat.postMessage", channel=data['channel'], text="Creating model for " + user + "...",
                        username='monkeybot', icon_url='https://avatars.slack-edge.com/2016-04-22/36974811941_432c34a832558067e693_48.png'
                    )

                    try:
                        module_ids[user] = create_module_user(user, ml, slack, f)
                        f2 = open('user_modules.pickle', 'wb')
                        pickle.dump(module_ids, f2)
                        f2.close()
                        outputs.append([data['channel'], 'Done! :)'])
                    except:
                        outputs.append([data['channel'], 'Hmmm sorry unexpected error :( try again!'])
                    return

                elif command == '\delete':

                    if len(args_list) > 0:
                        user = args_list[0]

                    if user in module_ids.keys():
                        sc.api_call(
                            "chat.postMessage", channel=data['channel'], text="Deleting model for " + user + "...",
                            username='monkeybot', icon_url='https://avatars.slack-edge.com/2016-04-22/36974811941_432c34a832558067e693_48.png'
                        )

                        try:
                            ml.classifiers.delete(module_ids[user])
                            del module_ids[user]
                            f2 = open('user_modules.pickle', 'wb')
                            pickle.dump(module_ids, f2)
                            f2.close()
                            outputs.append([data['channel'], 'Done.'])
                        except:
                            outputs.append([data['channel'], 'Hmmm sorry unexpected error :( try again!'])
                        return
                    else:
                        outputs.append([data['channel'], "It seems that " + user + "is not registered..."])
                        return

                outputs.append([data['channel'], "What? I don't understand you dude"])
                return
            else:
                # standard channel message
                channel = get_channel_name(data['channel'])
                user = get_user_name(data['user'])
                message = {
                    'ts': datetime.fromtimestamp(float(data['ts'])),
                    'text': data['text'],
                    'user': user
                }
        else:
            if data['channel'].startswith('D'):
                return

            channel = get_channel_name(data['channel'])
            user = get_user_name(data['message']['user'])
            if 'text' in data['message']['attachments'][0]:
                text = data['message']['attachments'][0]['text']
            elif 'title' in data['message']['attachments'][0]:
                text = data['message']['attachments'][0]['title']
            else:
                return

            message = {
                'ts': datetime.fromtimestamp(float(data['ts'])),
                'text': text,
                'user': user
            }

        # discard messages that are just a paste of url, we'll get the enriched version
        if message['text'].startswith('<http'):
            return

        print 'MESSAGE:'
        print channel, user
        print message
        print

        if channel == 'monkey-bot':
            return

        if channel in current_convs:
            current_conv = current_convs[channel]

            if is_in_conversation(message, current_conv):
                current_conv['messages'].append(message)
                current_conv['text'] += ' ' + message['text']
                current_conv['authors'].add(user)
            else:
                if channel not in historical_convs:
                    historical_convs[channel] = []
                historical_convs[channel].append(current_conv)
                current_conv = create_conversation(message['ts'], [message], message['text'], set([message['user']]))
                current_convs[channel] = current_conv
        else:
            current_conv = create_conversation(message['ts'], [message], message['text'], set([message['user']]))
            current_convs[channel] = current_conv

        #### SINGLE LABEL BINARY CLASSIFICATION

        notifications = []

        print "\n----- PREDICTIONS ------"
        print 'authors:', current_conv['authors']
        print 'alerted', current_conv['alerted']
        print current_conv['text']
        print

        for user in module_ids.keys():
            if user in current_conv['authors'] or user in current_conv['alerted']:
                continue

            res = ml.classifiers.classify(module_ids[user], [current_conv['text']] , sandbox=True)
            print user

            print res.result[0][0]

            if res.result[0][0]['label'] == 'yes' and res.result[0][0]['probability'] > config['SUGGESTION_THRESHOLD']:
                notifications.append(user)
                current_conv['alerted'].add(user)

        if len(notifications):
            outputs.append([data['channel'], 'Hey @' + ' @'.join(notifications)])

    except Exception as e:
        print 'Unexpected error'
        print e.message
        traceback.print_exc()
