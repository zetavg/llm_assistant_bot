# LLM Assistant Bot

LLM powered Slack Bot for assisting you and your team.

> This is a work in progress and currently have the following security concerns:
> 
> 1. It's possible that the bot will leak confidential information by searching on Google with those information as the keyword.
> 2. It's possible that the user can trick the bot to execute arbitrary code with the Python REPL tool.

Possible use cases: FAQ help desk, new team member onboarding, etc.

Using tools:

https://github.com/zetavg/llm_assistant_bot/assets/3784687/be18a77b-b4bc-4aba-9ce8-2924fa20bca2

Memory, answer questions based on memorized knowledge or imported documents:

![](https://github.com/zetavg/llm_assistant_bot/assets/3784687/ba98ece4-1820-4f33-97cd-dd5d22427e9a)


## Up and Running

After preparing the environment (such as `conda create python=3.8 -n llm_assistant_bot`),

1. `pip install -r requirements.txt`.
2. `playwright install`.
3. `cp config.yaml.sample config.yaml` and fill in the blanks.
4. `python slack_bot.py`.

To enter the console, run `python console.py`.


## Chat Integrations

### Slack Bot

First, create a new app at https://api.slack.com/apps?new_app.

Choice "From an app manifest", and paste the following with `# Fill me!`s replaced:

```yaml
display_information:
  name: # Fill me!
features:
  bot_user:
    display_name: # Fill me!
    always_online: false
oauth_config:
  scopes:
    bot:
      - pins:read
      - reactions:read
      - users:read
      - channels:history
      - groups:history
      - chat:write
      - im:history
      - im:read
      - im:write
      - mpim:history
      - mpim:read
      - mpim:write
settings:
  event_subscriptions:
    # Example: https://example.com/slack/events
    request_url: # Fill me!
    bot_events:
      - message.channels
      - message.groups
      - message.im
      - message.mpim
      - pin_added
      - reaction_added
      - team_join
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false
```

Then, get the `Signing Secret` of the app and fill it in `config.yaml`.

<details>
  <summary>Details</summary>
  <img src="https://github.com/zetavg/llm_assistant_bot/assets/3784687/e7e1e88e-a475-40ae-82aa-d9390283d839" />
</details>

Also, make sure the Request URL of Event Subscription works.

<details>
  <summary>Details</summary>
  <img src="https://github.com/zetavg/llm_assistant_bot/assets/3784687/6b40e9ac-55dc-4225-acf2-bc8bd9d2e683" />
</details>

Finally, install the app to your workspace, get the `Bot User OAuth Token` of the app and fill it in `config.yaml`.

<details>
  <summary>Details</summary>
  <img src="https://github.com/zetavg/llm_assistant_bot/assets/3784687/6b534b9a-1885-4a23-af7c-2855e0600e9a" />
</details>

To let users send direct messages to the bot, `Allow users to send Slash commands and messages from the messages tab` should be enabled in the bot's settings.

<details>
  <summary>Details</summary>
  <img src="https://github.com/zetavg/llm_assistant_bot/assets/3784687/f4dfe1fa-67ff-4df7-bb6e-323143a50aea" />
</details>

## Importing Documents

```bash
python console.py
```

```py
sitemap_loader = langchain.document_loaders.sitemap.SitemapLoader(web_path="https://langchain.readthedocs.io/sitemap.xml")
docs = sitemap_loader.load()

text_splitter = langchain.text_splitter.CharacterTextSplitter.from_tiktoken_encoder(chunk_size=100, chunk_overlap=0)
docs = text_splitter.split_documents(docs)

add_docs('langchain_docs', docs)
```

(See: https://python.langchain.com/en/latest/modules/indexes/document_loaders.html)
