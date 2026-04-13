class AdvisorService:
    def chat(self, user_id, question):
        return {
            "answer": "Advisor service is ready.",
            "behavior_segment": "casual_buyer",
            "recommended_books": [],
            "sources": [],
        }
