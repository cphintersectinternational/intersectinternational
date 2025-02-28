import streamlit as st
from docx import Document
from io import BytesIO
import pandas as pd
import re
from openai import OpenAI
import json

openai_api_key = st.secrets["openai"]["openai_api_key"]
client = OpenAI(api_key=openai_api_key)

# Function to convert DOCX to text
def convert_docx_to_txt_memory(docx_file):
    docx_bytes = BytesIO(docx_file.getvalue())
    doc = Document(docx_bytes)
    return '\n'.join(paragraph.text for paragraph in doc.paragraphs)

def clear_cache():
    keys = list(st.session_state.keys())
    for key in keys:
        st.session_state.pop(key)
    

st.set_page_config(
    page_title="Intersect International",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "This is a tool to help you analyze qualitative data from interviews. It uses OpenAI's models to extract themes and verbatim quotes from your data."
    }
)

# Initialize session state
if "uploaded_files_text" not in st.session_state:
    st.session_state["uploaded_files_text"] = None

if "uploaded_files_metadata" not in st.session_state:
    st.session_state["uploaded_files_metadata"] = None

if "theme_response" not in st.session_state:
    st.session_state["theme_response"] = None

if "theme_response_updated" not in st.session_state:
    st.session_state["theme_response_updated"] = None

if "output_quotes" not in st.session_state:
    st.session_state["output_quotes"] = None

sidebar = st.sidebar
sidebar.image("logo.png", width=100)
sidebar.caption("Welcome to the Intersect Agent")


modelSelected = sidebar.selectbox("Select a model", ["gpt-4o-mini", "gpt-4o"], index=0)
sidebar.button('Clear Results', on_click=clear_cache)


tab1, tab2, tab3= st.tabs(["Document Settings", "Standard Theme Output", "Open Chat"])

with tab1:

    #Upload files
    st.title("⚙️ Document settings")
    st.subheader("1) Upload documents")
    uploaded_files = st.file_uploader(
        "Upload a document (.doc or .docx)", type=("doc", "docx"), accept_multiple_files=True
    )

    #Convert files to text and clean
    if uploaded_files:

        df = pd.DataFrame({"filename": [file.name for file in uploaded_files]})
        df['participant'] = ""
        st.caption("Please add participant names to the documents")
        upload_files_metadata = st.data_editor(
            df,
            use_container_width=True,
            disabled=["filename"],
            hide_index = True,
            column_config={
                "fileName": st.column_config.TextColumn(label="File Name"),
                "participant": st.column_config.TextColumn(label="Participant Name"),
                }
        )

        uploaded_files_text = []
        for file in uploaded_files:
            text = convert_docx_to_txt_memory(file)
            text = re.sub(r'\n{3,}', '\n\n', text)
            uploaded_files_text.append(text)

        st.divider()
        st.subheader("2) Alias words")
        st.caption("Add words to alias. For example, if you want to alias 'Apple Ltd' to '[company_1]', add 'Apple Ltd' in the first column and 'company' in the second column. You can add multiple words separated by commas.")
        aliases = st.data_editor(
            pd.DataFrame(columns=[ "type","alias"]),
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "type": st.column_config.SelectboxColumn(label="Type", options=["company", "group", "participant"]),
                "alias": st.column_config.TextColumn(label="Words to Alias"),
                
                }
        )
        aliases['type_occurance'] = aliases.groupby('type').cumcount() + 1
        aliases['alias_mask'] = "["+aliases['type'] +"_"+ aliases['type_occurance'].astype(str)+"]"
        aliases.drop('type_occurance', axis=1, inplace=True)
        
        for i, row in aliases.iterrows():
            if row['alias']:
                words_to_alias = [word.strip() for word in row['alias'].split(",") if word.strip()]
                for word in words_to_alias:
                    for j in range(len(uploaded_files_text)):
                        uploaded_files_text[j] = uploaded_files_text[j].replace(word.lower(), row['alias_mask'])
                        uploaded_files_text[j] = uploaded_files_text[j].replace(word.upper(), row['alias_mask'])
                        uploaded_files_text[j] = uploaded_files_text[j].replace(word.title(), row['alias_mask'])
                        uploaded_files_text[j] = uploaded_files_text[j].replace(word.capitalize(), row['alias_mask'])

        st.divider()
        st.subheader('3) Review updated documents')
        for i, item in enumerate(uploaded_files_text):
            with st.expander(upload_files_metadata["filename"][i], expanded=False):
                st.text_area("", item, height=500)
        
        st.session_state["uploaded_files_text"] = uploaded_files_text
        st.session_state["uploaded_files_metadata"] = upload_files_metadata
        #check is metadata is missing participant
        empty_participant = len(upload_files_metadata[upload_files_metadata["participant"] == ""]) > 0
       
with tab2:
    
    st.title("📄 Standard theme output")
    if uploaded_files and not empty_participant:
        st.subheader("1) Define themes")
        
        onAi = st.toggle("Use AI to define themes", value=False)
        if onAi:
          
            theme_groups = st.text_area(
                "Define grouping for themes",
                placeholder="Provide how you want to group themes, such as: 1) What can be improved 2) What is working"
            )
            theme_numbers = st.slider("Select max number of themes per group", 1, 10, 5)
            setThemeTemperature = st.slider("Select temperature for theme generation (0=No randomness, 1=Default)", 0.0, 1.0, 1.0, 0.1)
            executeThemeButton = st.button("Get Themes", disabled= not theme_groups.strip())
            if executeThemeButton:
                with st.spinner('Processing...'):
                    messages = [
                        {
                            "role": "system",
                            "content": f"You will receive a set of interview responses. Please group key themes based on the groups provided by the user. Provide {theme_numbers} themes for each of the groups"
                        },
                        {
                            "role": "user",
                            "content": f"""
                                ---
                                The interview responses are listed below:
                                {json.dumps(st.session_state["uploaded_files_text"])}
                                
                                ---
                                The groupings for themes are listed below:
                                {theme_groups}"""
                        }
                    ]

                    response = client.chat.completions.create(
                        model= modelSelected,
                        messages=messages,
                        stream=False,
                        temperature=setThemeTemperature,
                        response_format={
                            "type":"json_schema",
                            "json_schema":{
                                "name":"response",
                                "schema":{
                                "type":"object",
                                "properties":{
                                    "themes":{
                                        "type":"array",
                                        "items":{
                                            "type":"object",
                                            "properties":{
                                                "group":{
                                                    "type":"string"
                                                },
                                                "theme":{
                                                    "type":"string"
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            }
                        }
                    )
                    st.session_state["theme_response"] = json.loads(response.choices[0].message.content)["themes"]
        else:
            st.session_state["theme_response"] = [
                {"group": None, "theme": None}
            ]
                
        if st.session_state["theme_response"]:
            st.caption("Themes: Themes can be manually added, edited and removed if required")
            st.session_state["theme_response_updated"] = st.data_editor(
                st.session_state["theme_response"],
                use_container_width=True,
                
                num_rows="dynamic",
                hide_index = True,
                column_config={
                    "group": st.column_config.TextColumn(label="Group"),
                    "theme": st.column_config.TextColumn(label="Theme"),
                    }
            )
            
        #filter st.session_state["theme_response_updated"] where theme is not None or ""
        if len([x for x in st.session_state["theme_response_updated"] if x['theme'] not in [None, ""]])> 0:
            st.divider()
            st.subheader("2) Get verbatim quotes")
            quote_number = st.slider(
                "Select max number of quotes per participant per theme", 1, 5, 1
            )

            setQuoteTemperature = st.slider("Select temperature for Quote generation (0=No randomness, 1=Default)", 0.0, 1.0, 0.3, 0.1)

            additional_notes = st.text_area(
                "Add any additional notes to be included in the prompt",
                placeholder="Input notes here"
            )
            
            execute_verbatim_button = st.button("Get Quotes")

            if execute_verbatim_button:
                with st.spinner('Processing...'):

                    def get_verbatim_quotes(text, themes):
                        prompt = f"""
                            ---
                            Only provide {quote_number} verbatim quote(s) per theme.

                            ---

                            The themes are listed below:
                            {themes}
                            -----------

                            The survey response is listed below:
                            {text}

                            If applicable, in your response keep entities such as company_, group_ and participant_ as is with [] brackets

                            ---
                            Consider these additional notes:
                            {additional_notes}
                            """
                        messages = [
                            {"role": "system", "content": "You are a helpful assistant who finds verbatim quotes for themes within survey responses"},
                            {"role": "user", "content": prompt}
                        ]
                        response = client.chat.completions.create(
                            model=modelSelected,
                            messages=messages,
                            stream=False,
                            temperature=setQuoteTemperature,
                            response_format={
                                    "type":"json_schema",
                                    "json_schema":{
                                        "name":"response",
                                        "schema":{
                                        "type":"object",
                                        "properties":{
                                            "quotes":{
                                                "type":"array",
                                                "items":{
                                                    "type":"object",
                                                    "properties":{
                                                        "group":{
                                                            "type":"string"
                                                        },
                                                        "theme":{
                                                            "type":"string"
                                                        },
                                                        "quote":{
                                                            "type":"string"
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    }
                                }
                            )
                        
                        return json.loads(response.choices[0].message.content)["quotes"]
                    
                    #Cycle through each file and get quotes
                    all_quotes = []
                    for text_index, text in enumerate(st.session_state["uploaded_files_text"]):
                        quotes = get_verbatim_quotes(
                            text, 
                            json.dumps(st.session_state["theme_response_updated"])
                        )
                        # Append participant to each quote
                        for quote in quotes:
                            quote["participant"] = st.session_state["uploaded_files_metadata"]["participant"][text_index]
                        all_quotes.extend(quotes)

                    ##Prepare quotes for writability
                    #resort quotes to put quotes in a dict with group and theme as keys
                    resorted_quotes = {}
                    for quote in all_quotes:
                        group = quote["group"]
                        theme = quote["theme"]
                        quote_text = quote["quote"]
                        participant = quote["participant"]

                        if group not in resorted_quotes:
                            resorted_quotes[group] = {}

                        if theme not in resorted_quotes[group]:
                            resorted_quotes[group][theme] = []

                        resorted_quotes[group][theme].append({"quote": quote_text, "participant": participant})

                    #covert the resorted structure to a string for display
                    output_quotes = ""
                    for group, themes in resorted_quotes.items():
                        output_quotes += f"### {group}\n\n"
                        for theme, quotes in themes.items():
                            output_quotes += f"#### {theme}\n\n"
                            for quote in quotes:
                                output_quotes += f"- {quote['quote']} ({quote['participant']})\n"
                            output_quotes += "\n"

                    #where output_quotes has word alias_mask replace it back with the original word
                    for i, row in aliases.iterrows():
                        if row['alias']:
                            words_to_alias = [word.strip() for word in row['alias'].split(",") if word.strip()]
                            for word in words_to_alias:
                                output_quotes = output_quotes.replace(row['alias_mask'], word)
                    
                    
                    st.caption("Verbatim Quotes")
                    with st.container(border=True):
                        st.write(output_quotes)
    else:
        st.warning("Please upload documents in the Document Settings tab and ensure they all have an assigned participant")

with tab3:
    st.title("💬 Open chat")
    if uploaded_files and not empty_participant:
        open_question = st.text_area(
            "Ask any question about the uploaded files",
            placeholder="Input question here"
        )
        participantsSelected = st.multiselect(
        "Select files to use",
        options=st.session_state["uploaded_files_metadata"]["participant"]
        )
        
        #filter uploaded files to only those selected
        if participantsSelected:
            filtered_uploaded_files_text = [st.session_state["uploaded_files_text"][i] for i in range(len(st.session_state["uploaded_files_metadata"])) if st.session_state["uploaded_files_metadata"]["participant"][i] in participantsSelected]
        else:
            filtered_uploaded_files_text = st.session_state["uploaded_files_text"]
        
        setChatTemperature = st.slider("Select temperature for Chat generation (0=No randomness, 1=Default)", 0.0, 1.0, 1.0, 0.1)
        execute_response_button = st.button("Get Response", disabled=not st.session_state["uploaded_files_text"])
        if execute_response_button:
            with st.spinner('Processing...'):
                messages = [
                    {
                        "role": "system",
                        "content": f"You will receive a set of interview responses. Please answer the question based on the responses provided by the user."
                    },
                    {
                        "role": "user",
                        "content": f"""
                            ---
                            The interview responses are listed below:
                            {json.dumps(filtered_uploaded_files_text)}

                            If applicable, in your response keep entities such as company_, group_ and participant_ as is with [] brackets
                            
                            ---
                            The question is listed below:
                            {open_question}"""
                    }
                ]

                open_response = client.chat.completions.create(
                    model=modelSelected,
                    messages=messages,
                    temperature=setChatTemperature,
                    stream=False
                )

                open_response = open_response.choices[0].message.content
                
                #where output_quotes has word alias_mask replace it back with the original word
                for i, row in aliases.iterrows():
                    if row['alias']:
                        words_to_alias = [word.strip() for word in row['alias'].split(",") if word.strip()]
                        for word in words_to_alias:
                            open_response = open_response.replace(row['alias_mask'], word)
                with st.container(border=True):
                    st.write(open_response)
    else:
        st.warning("Please upload documents in the Document Settings tab and ensure they all have an assigned participant")


    
    
            