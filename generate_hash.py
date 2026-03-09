import streamlit_authenticator as stauth
import yaml

with open('.streamlit/config.yaml', 'r') as file:
    config = yaml.safe_load(file)

hashed_passwords = stauth.Hasher(['admin']).generate()

config['credentials']['usernames']['admin']['password'] = hashed_passwords[0]

with open('.streamlit/config.yaml', 'w') as file:
    yaml.dump(config, file, default_flow_style=False)
