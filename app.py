import gcimport sysimport timeimport pandas as pdimport streamlit as stfrom streamlit_server_state import no_rerun, server_statefrom helper.modelling import determine_rerun_reinitialize, initialize, set_static_model_paramsfrom helper.own_corpus import check_table_exists, check_db_exists, process_corpus, transfer_dbfrom helper.progress_bar import Loggerfrom helper.ui import export_chat_history, import_styles, streamed_responsefrom helper.user_management import calc_max_users, check_password, clear_models, determine_availability, manage_boot, setup_local_files, update_server_state### session initialization/loginif "user_name" in st.session_state:    from helper.user_management import record_usedetermine_availability()if not check_password():    st.stop()  # Do not continue if check_password is not True.        ###  app setup# headerst.title("Local LLM")if "master_db_name" not in st.session_state:    st.session_state["master_db_name"] = "vector_db"if "db_name" not in st.session_state:    st.session_state["db_name"] = st.session_state["user_name"].lower().replace(" ", "_")    # check if first boot of user and check if eligible to be kicked offmanage_boot()        # styles sheetsimport_styles()# LLM set up# parameters/authenticationsetup_local_files()# placeholder on initial loadif f'model_{st.session_state["db_name"]}' not in server_state:    st.markdown("""<div class="icon_text"><img width=50 src='https://www.svgrepo.com/show/375527/ai-platform.svg'></div>""", unsafe_allow_html=True)    st.markdown("""<div class="icon_text"<h4>What would you like to know?</h4></div>""", unsafe_allow_html=True) ## sidebar# upload your own documents    st.sidebar.markdown("# Upload your own documents", help = "Enter the name of your corpus in the `Corpus name` field. If named `temporary`, it will be able to be written over after your session.")# paste a list of web urlsst.session_state["own_urls"] = st.sidebar.text_input(   "URLs",   value="" if "own_urls" not in st.session_state else st.session_state["own_urls"],   help="A comma separated list of URLs.")st.session_state["uploaded_file"] = st.sidebar.file_uploader("Upload your own documents",type=[".zip", ".docx", ".doc", ".txt", ".pdf", ".csv"], help="Upload either a single `metadata.csv` file, with at least one column named `web_filepath` with the web addresses of the .html or .pdf documents, or upload a .zip file that contains a folder named `corpus` with the .csv, .doc, .docx, .txt, or .pdf files inside. You can optionally include a `metadata.csv` file in the zip file at the same level as the `corpus` folder, with at least a column named `filename` with the names of the files. If you want to only include certain page numbers of PDF files, in the metadata include a column called 'page_numbers', with the pages formatted as e.g., '1,6,9:12'.")process_corpus_button = st.sidebar.button('Process corpus', help="Click if you uploaded your own documents or pasted your own URLs.")st.sidebar.divider()# model paramsst.sidebar.markdown("# Model parameters", help="Click the `Reinitialize model` button if you change any of these parameters.")# which_llmst.session_state["selected_llm"] = st.sidebar.selectbox(   "Which LLM",   options=st.session_state["llm_dict"].name,   index=tuple(st.session_state["llm_dict"].name).index("mistral-docsgpt") if "selected_llm" not in st.session_state else tuple(st.session_state["llm_dict"].name).index(st.session_state["selected_llm"]),   help="Which LLM to use.")# which corpusst.session_state["selected_corpus"] = st.sidebar.selectbox(   "Which corpus",   options=["None"] + sorted([x for x in list(st.session_state["corpora_dict"].name) if "temporary" not in x or x == f"temporary_{st.session_state['db_name']}"]), # don't show others' temporary corpora   index=0 if "selected_corpus" not in st.session_state else tuple(["None"] + sorted([x for x in list(st.session_state["corpora_dict"].name) if "temporary" not in x or x == f"temporary_{st.session_state['db_name']}"])).index(st.session_state["selected_corpus"]),   help="Which corpus to contextualize on.")with st.sidebar.expander("Advanced model parameters"):    # renaming new corpus    st.session_state["new_corpus_name"] = st.text_input(       "Uploaded corpus name",       value=f"temporary_{st.session_state['db_name']}" if "new_corpus_name" not in st.session_state else st.session_state["new_corpus_name"],       help="The name of the new corpus you are processing. It must be able to be a SQL database name, so only lower case, no special characters, no spaces. Use underscores."    )        # similarity top k    st.session_state["similarity_top_k"] = st.slider(       "Similarity top K",       min_value=1,       max_value=20,       step=1,       value=4 if "similarity_top_k" not in st.session_state else st.session_state["similarity_top_k"],       help="The number of contextual document chunks to retrieve for RAG."    )        # n_gpu layers    st.session_state["n_gpu_layers"] = 100 if "n_gpu_layers" not in st.session_state else st.session_state["n_gpu_layers"]        # temperature    st.session_state["temperature"] = st.slider(       "Temperature",       min_value=0,       max_value=100,       step=1,       value=0 if "temperature" not in st.session_state else st.session_state["temperature"],       help="How much leeway/creativity to give the model, 0 = least creativity, 100 = most creativity."    )        # max_new tokens    st.session_state["max_new_tokens"] = st.slider(       "Max new tokens",       min_value=16,       max_value=16000,       step=8,       value=512 if "max_new_tokens" not in st.session_state else st.session_state["max_new_tokens"],       help="How long to limit the responses to (token ≈ word)."    )        # context window    st.session_state["context_window"] = st.slider(       "Context window",       min_value=500,       max_value=50000,       step=100,       value=4000 if "context_window" not in st.session_state else st.session_state["context_window"],       help="How large to make the context window for the LLM. The maximum depends on the model, a higher value might result in context window too large errors."    )        # memory limit    st.session_state["memory_limit"] = st.slider(       "Memory limit",       min_value=80,       max_value=80000,       step=8,       value=2048 if "memory_limit" not in st.session_state else st.session_state["memory_limit"],       help="How many tokens (words) memory to give the chatbot."    )        # system prompt    st.session_state["system_prompt"] = st.text_input(       "System prompt",       value=""  if "system_prompt" not in st.session_state else st.session_state["system_prompt"],       help="What prompt to initialize the chatbot with."    )    # params that affect the vector_db    st.markdown("# Vector DB parameters", help="Changing these parameters will require remaking the vector database and require a bit longer to run. Push the `Reinitialize model and remake DB` button if you change one of these.")        # chunk overlap    st.session_state["chunk_overlap"] = st.slider(       "Chunk overlap",       min_value=0,       max_value=1000,       step=1,       value=200 if "chunk_overlap" not in st.session_state else st.session_state["chunk_overlap"],       help="How many tokens to overlap when chunking the documents."    )        # chunk size    st.session_state["chunk_size"] = st.slider(       "Chunk size",       min_value=64,       max_value=6400,       step=8,       value=512 if "chunk_size" not in st.session_state else st.session_state["chunk_size"],       help="How many tokens per chunk when chunking the documents."    )        reinitialize_remake = st.button('Reinitialize model and remake DB', help="Click if you make any changes to the vector DB parameters.")# reinitialize model buttonreinitialize = st.sidebar.button('Reinitialize model', help="Click if you change the `Which LLM` or `Which corpus` options, or any of the advanced parameters.")st.sidebar.divider()# lockout dropdownlockout_options = [3, 10, 15, 20]st.session_state["last_used_threshold"] = st.sidebar.selectbox(   "Lockout duration",   options=lockout_options,   index=0 if "last_used_threshold" not in st.session_state else lockout_options.index(st.session_state["last_used_threshold"]),   help="How many minutes after each interaction to continue reserving your session.")reset_memory = st.sidebar.button("Reset model's memory", help="Reset the model's short-term memory to start with a fresh model")    # static model paramsset_static_model_params()# determine if the database needs to be reinitializeddetermine_rerun_reinitialize()# loading modelif f'model_{st.session_state["db_name"]}' not in server_state or reinitialize or reinitialize_remake or process_corpus_button:    if process_corpus_button:        if not((st.session_state["new_corpus_name"] == f"temporary_{st.session_state['db_name']}") or (st.session_state["new_corpus_name"] not in list(st.session_state["corpora_dict"].name.values))):            st.error("A corpus with this name already exists, choose another one.")        else:            with st.spinner('Processing corpus...'):                record_use(future_lock=True)                old_stdout = sys.stdout                sys.stdout = Logger(st.progress(0), st.empty())                st.session_state["corpora_dict"] = process_corpus(user_name=st.session_state["db_name"], corpus_name=st.session_state["new_corpus_name"], own_urls=st.session_state["own_urls"], uploaded_document=st.session_state["uploaded_file"])                record_use(future_lock=False)                            st.session_state["selected_corpus"] = st.session_state["new_corpus_name"]            st.session_state.messages = [] # clear out message history on the prior context            clear_models()        with st.spinner('Initializing...'):        # whether or not to remake the vector DB        if reinitialize_remake or process_corpus_button:            rerun_populate_db = True            clear_database_local = st.session_state["clear_database"]        else:            rerun_populate_db = st.session_state["rerun_populate_db"]            clear_database_local = st.session_state["clear_database"]                    def model_initialization():            model, st.session_state["which_llm"], st.session_state["which_corpus"] = initialize(                which_llm_local=st.session_state["selected_llm"],                which_corpus_local=None if st.session_state["selected_corpus"] == "None" else st.session_state["selected_corpus"],                n_gpu_layers=st.session_state["n_gpu_layers"],                temperature=st.session_state["temperature"] / 1e2, # convert 1-100 to 0-1                max_new_tokens=st.session_state["max_new_tokens"],                context_window=st.session_state["context_window"],                memory_limit=st.session_state["memory_limit"],                chunk_overlap=st.session_state["chunk_overlap"],                chunk_size=st.session_state["chunk_size"],                paragraph_separator=st.session_state["paragraph_separator"],                separator=st.session_state["separator"],                system_prompt=st.session_state["system_prompt"],                rerun_populate_db=rerun_populate_db,                clear_database_local=clear_database_local,                corpora_dict=st.session_state["corpora_dict"],                llm_dict=st.session_state["llm_dict"],                db_name=st.session_state["db_name"],                db_info=st.session_state["db_info"],            )            update_server_state(f'model_{st.session_state["db_name"]}', model)            del model            gc.collect()                record_use(future_lock=True)        model_initialization()        record_use(future_lock=False)                # clear the progress bar        if rerun_populate_db:            sys.stdout = sys.stdout.clear()            sys.stdout = old_stdout                    # copy the new table to master vector_db if it's not already there        if not(check_table_exists(user=st.session_state["db_info"].loc[0, 'user'], password=st.session_state["db_info"].loc[0, 'password'], db_name=st.session_state["master_db_name"], table_name=f"data_{st.session_state['which_corpus']}")):            # close the model connection to not have simulataneous ones            clear_models()                        # transfer the db            transfer_db(user=st.session_state["db_info"].loc[0, 'user'], password=st.session_state["db_info"].loc[0, 'password'], source_db=st.session_state["db_name"], target_db=st.session_state["master_db_name"])                        # reinitialize the model            record_use(future_lock=True)            model_initialization()            record_use(future_lock=False)                    st.session_state.messages = [] # clear out message history on the prior context        st.info("Model successfully initialized!")                update_server_state("max_users", calc_max_users(len(server_state["queue"])))if f'model_{st.session_state["db_name"]}' in server_state:    # Initialize chat history    if "messages" not in st.session_state:        st.session_state.messages = []        # Display chat messages from history on app rerun    for message in st.session_state.messages:        avatar = st.session_state["user_avatar"] if message["role"] == "user" else st.session_state["assistant_avatar"]        with st.chat_message(message["role"], avatar=avatar):            if "source_string" not in message["content"]:                st.markdown(message["content"])            else:                st.markdown("Sources: ", unsafe_allow_html=True, help=message["content"].split("string:")[1])                    # reset model's memory    if reset_memory:        if server_state[f'model_{st.session_state["db_name"]}'].chat_engine is not None:            with no_rerun:                server_state[f'model_{st.session_state["db_name"]}'].chat_engine.reset()        with st.chat_message("assistant", avatar=st.session_state["assistant_avatar"]):            st.markdown("Model memory reset!")        st.session_state.messages.append({"role": "assistant", "content": "Model memory reset!"})        # Accept user input    if st.session_state["which_corpus"] is None:        placeholder_text = f"""Query '{st.session_state["which_llm"]}', not contextualized"""    else:        placeholder_text = f"""Query '{st.session_state["which_llm"]}' contextualized on '{st.session_state["which_corpus"]}' corpus"""            if prompt := st.chat_input(placeholder_text):        # Display user message in chat message container        with st.chat_message("user", avatar=st.session_state["user_avatar"]):            st.markdown(prompt)        # Add user message to chat history        st.session_state.messages.append({"role": "user", "content": prompt})                if st.session_state.messages[-1]["content"].lower() == "clear":            clear_models()                with st.chat_message("assistant", avatar=st.session_state["assistant_avatar"]):                st.markdown("Models cleared!")            st.session_state.messages.append({"role": "assistant", "content": "Models cleared!"})        else:            # lock the model to perform requests sequentially            if "in_use" not in server_state:                update_server_state("in_use", False)                            if "exec_queue" not in server_state:                update_server_state("exec_queue", [st.session_state["user_name"]])            if len(server_state["exec_queue"]) == 0:                update_server_state("exec_queue", [st.session_state["user_name"]])            else:                if st.session_state["user_name"] not in server_state["exec_queue"]:                    # add to the queue                    update_server_state("exec_queue", server_state["exec_queue"] + [st.session_state["user_name"]])                            with st.spinner('Query queued...'):                t = st.empty()                while server_state["in_use"] or server_state["exec_queue"][0] != st.session_state["user_name"]:                    t.markdown(f'You are place {server_state["exec_queue"].index(st.session_state["user_name"])} of {len(server_state["exec_queue"]) - 1}')                    time.sleep(1)                t.empty()                                # lock the model while generating            update_server_state("in_use", True)            record_use(future_lock=True)                            # generate response                            response = server_state[f'model_{st.session_state["db_name"]}'].gen_response(                st.session_state.messages[-1]["content"],                similarity_top_k=st.session_state["similarity_top_k"],                use_chat_engine=st.session_state["use_chat_engine"],                reset_chat_engine=st.session_state["reset_chat_engine"],                streaming=True,            )            # Display assistant response in chat message container            with st.chat_message("assistant", avatar=st.session_state["assistant_avatar"]):                st.write_stream(streamed_response(response["response"]))                    # adding sources            with st.chat_message("assistant", avatar=st.session_state["assistant_avatar"]):                if len(response.keys()) > 1: # only do if RAG                    # markdown help way                    source_string = ""                    counter = 1                    for j in list(pd.Series(list(response.keys()))[pd.Series(list(response.keys())) != "response"]):                        #source_string += f"**Source {counter}**:\n\n \t\t{response[j]}\n\n\n\n"                        metadata_dict = eval(response[j].split("| source text:")[0].replace("metadata: ", ""))                        metadata_string = ""                        for key, value in metadata_dict.items():                            if key != "is_csv":                                metadata_string += f"'{key}': '{value}'\n"                                                source_string += f"""# Source {counter}\n ### Metadata:\n ```{metadata_string}```\n ### Text:\n{response[j].split("| source text:")[1]}\n\n"""                        counter += 1                else:                    source_string = "NA"                st.markdown("Sources: ", unsafe_allow_html=True, help = f"{source_string}")                            # unlock the model            update_server_state("in_use", False)            update_server_state("exec_queue", server_state["exec_queue"][1:]) # take out of the queue                        record_use(future_lock=False)                    # Add assistant response to chat history            st.session_state.messages.append({"role": "assistant", "content": response["response"].response})            st.session_state.messages.append({"role": "assistant", "content": f"source_string:{source_string}"})            # export chat historyif "messages" in st.session_state:    export_chat_button = st.sidebar.download_button(        label="Export chat history",        data=export_chat_history(),        file_name="chat_history.MD",        help="Export the session's chat history to a formatted Markdown file. If you don't have a Markdown reader on your computer, post the contents to a [web app](http://editor.md.ipandao.com/en.html)"    )    # end session buttonend_session = st.sidebar.button("End session", help="End your session and free your spot.")if end_session:    clear_models()    record_use(free_up=True)    update_server_state("queue", [x for x in server_state["queue"] if x != st.session_state["user_name"]])    st.session_state["password_correct"] = False    st.rerun()    st.stop()    # help contactst.sidebar.markdown("*For questions on how to use this application or its methodology, please write [Author](mailto:someone@example.com)*", unsafe_allow_html=True)