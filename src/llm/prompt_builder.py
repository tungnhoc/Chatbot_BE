from src.llm.llm_client import generate_groq_response



def build_summary_prompt(history_str: str) -> str:
    
    if len(history_str) > 8000:
        history_str = history_str[-8000:]

    prompt = f"""
            You are an AI assistant that summarizes conversations between a user and a chatbot.

            Please read the conversation below and summarize it concisely and clearly.
            Automatically detect the language (Vietnamese or English) 
            and respond in the same language as the conversation.

            ---------------------
            {history_str}
            ---------------------

            Your summary should include:
            1. **Main topic** — what the user is asking about.
            2. **Key questions** — list the main questions from the user.
            3. **Important information provided** — key answers or facts from the assistant.
            4. **Context to remember** — any details useful for future questions.

            Keep the summary short (3–5 sentences), focusing only on essential information.
            """
    return prompt.strip()



def summarize_conversation(conversation_history: str):
    try:
        prompt = build_summary_prompt(conversation_history)
        summary = generate_groq_response(prompt)
        return summary.strip()
    except Exception as e:
        print("❌ Error summarizing conversation:", e)
        return "Unable to summarize this conversation."
    


def build_answer_prompt(user_query, retrieved_context, conversation_summary=None, messages_recently=None):
    prompt = f"""
            You are a helpful AI assistant that answers questions based on provided documents.

            IMPORTANT: Respond in the SAME LANGUAGE as the user's question.
            - If user asks in English → Answer in English.
            - If user asks in Vietnamese → Answer in Vietnamese.

            RELEVANT CONVERSATION SUMMARY:
            {conversation_summary if conversation_summary else "No relevant conversation summary."}

            RECENT MESSAGES (last few exchanges):
            {messages_recently if messages_recently else "None"}

            REFERENCE DOCUMENTS (from knowledge base or PDF):
            {retrieved_context}

            USER QUESTION:
            {user_query}

            INSTRUCTIONS:
            - Analyze all sources carefully (summary, chat, and documents).
            - Answer directly in the SAME LANGUAGE as the question.
            - Quote exact data from the documents when possible.
            - If the documents don’t contain the answer, say so clearly.
            - Be professional and concise.

            ANSWER:
            """
    return prompt.strip()
    


def build_answer_prompt_1(user_query, retrieved_context, conversation_summary=None, messages_recently=None):
    prompt = f"""
            You are an intelligent and helpful AI assistant that answers user 
            questions based on provided documents and past conversations.

            IMPORTANT:
            - Always respond in the SAME LANGUAGE as the user's question.
            (If the question is in English → answer in English; if in Vietnamese → answer in Vietnamese.)
            - Keep responses concise, accurate, and easy to understand.

            
            Summary of previous related conversation:
            {conversation_summary if conversation_summary else "No related summaries found."}

            Recent chat exchanges:
            {messages_recently if messages_recently else "No recent messages."}

            Reference documents (from PDF / knowledge base):
            {retrieved_context if retrieved_context else "No reference documents found."}

            User's question:
            {user_query}

            Guidelines for answering:
            - Use the above (summary, chat, and documents) information to answer as accurately as possible.
            - Prioritize understanding from conversation context first, then reference documents.
            - Quote numbers, facts, and names exactly from documents when possible.
            - If the answer cannot be found in the provided context, clearly state that.
            - Be polite, logical, and avoid speculation.

            Answer:
            """
    return prompt.strip()

def generate_answer(user_query, retrieved_context, conversation_summary=None, messages_recently=None):
    
    try:
        prompt = build_answer_prompt(user_query, retrieved_context, conversation_summary, messages_recently)
        response = generate_groq_response(prompt)  
        return response.strip()
    except Exception as e:
        print("❌ Error while calling Groq API:", e)
        return "Sorry, I'm unable to generate a response at the moment."
    
