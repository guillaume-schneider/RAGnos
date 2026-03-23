import os
import chainlit as cl
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_classic.chains.retrieval import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

PDF_PATH = "document_test.pdf"

@cl.on_chat_start
async def on_chat_start():
    """Cette fonction s'exécute au lancement de l'application"""
    
    msg = cl.Message(content=f"⏳ Traitement du document '{PDF_PATH}' en cours...")
    await msg.send()

    if not os.path.exists(PDF_PATH):
        msg.content = f"❌ Erreur : Veuillez placer un fichier nommé '{PDF_PATH}' dans le même dossier que app.py."
        await msg.update()
        return

    loader = PyPDFLoader(PDF_PATH)
    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)

    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    vectorstore = Chroma.from_documents(documents=splits, embedding=embeddings)
    
    retriever = vectorstore.as_retriever()

    llm = ChatOllama(model="mistral")

    system_prompt = (
        "Tu es un assistant juridique expert, strict et précis. "
        "Utilise UNIQUEMENT le contexte fourni ci-dessous pour répondre à la question. "
        "Si l'information ne s'y trouve pas, dis explicitement : 'Je ne trouve pas cette information dans le document fourni.' "
        "Ne génère aucune fausse information.\n\n"
        "Contexte extrait du document :\n{context}"
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}")
    ])

    question_answer_chain = create_stuff_documents_chain(llm, prompt)
    rag_chain = create_retrieval_chain(retriever, question_answer_chain)

    cl.user_session.set("rag_chain", rag_chain)

    msg.content = "✅ Document ingéré avec succès ! L'IA est prête. Posez-moi vos questions sur le document."
    await msg.update()


@cl.on_message
async def on_message(message: cl.Message):
    """Cette fonction s'exécute à chaque fois que l'utilisateur pose une question"""
    
    rag_chain = cl.user_session.get("rag_chain")

    if not rag_chain:
        await cl.Message(content="⚠️ L'IA n'est pas initialisée correctement.").send()
        return

    msg = cl.Message(content="")
    await msg.send()

    res = await rag_chain.ainvoke({"input": message.content})

    msg.content = res["answer"]
    await msg.update()
