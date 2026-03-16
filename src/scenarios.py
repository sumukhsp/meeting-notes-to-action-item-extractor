from __future__ import annotations

SCENARIOS: dict[str, str] = {
    "scenario_01_basic": """User: Hi, can you tell me what the capital of France is?
Assistant: The capital of France is Paris.
User: Can you also tell me the population of Paris?
Assistant: Paris has a population of about 2.1 million people within the city limits.
User: Thank you.
Assistant: You're welcome!
User: That was helpful.
Assistant: Glad I could help.
User: Have a good day.
Assistant: You too!""",
    "scenario_02_bug": """User: I tried to generate a report but the system crashed.
Assistant: I'm sorry to hear that. What error message did you receive?
User: It says “Unexpected system error.”
Assistant: Did the error appear after clicking the generate button?
User: Yes, exactly after that.
Assistant: This might indicate a bug in the reporting module.
User: Is there a workaround?
Assistant: You could try refreshing the page or exporting the data manually.
User: I’ll try that.
Assistant: Let me know if the issue persists.""",
    "scenario_03_research": """User: I need help researching renewable energy sources.
Assistant: Sure, are you focusing on any particular type?
User: Solar and wind energy mainly.
Assistant: Solar energy uses sunlight to produce electricity through photovoltaic cells.
Assistant: Wind energy generates power using turbines driven by wind.
User: Which one is more efficient?
Assistant: It depends on location and weather conditions.
User: Can you provide examples of countries using them?
Assistant: Germany and Denmark use wind energy extensively.
User: Great, thanks for the information.""",
    "scenario_04_admin": """User: I need to update user permissions in the system.
Assistant: Do you have administrator access?
User: Yes, I’m the system admin.
Assistant: Please open the admin dashboard.
Assistant: Navigate to the user management section.
User: I see the user list now.
Assistant: Select the user and modify their role.
User: Should I assign editor access?
Assistant: Yes, if they need content editing privileges.
User: Done, the changes are saved.""",
    "scenario_05_deliverable": """User: I need a summary report for our weekly meeting.
Assistant: What topics should be included?
User: Sales performance and customer feedback.
Assistant: Sales increased by 12% this week.
Assistant: Customer feedback highlighted faster delivery times.
User: That sounds good.
Assistant: I’ll structure the report with key highlights and conclusions.
User: Please add a short recommendation section.
Assistant: Sure, I’ll include suggested improvements.
User: Perfect, that will work for the meeting.""",
    "scenario_06_multiple": """User: Can you help me with two things?
Assistant: Sure, what do you need?
User: First, calculate 25 plus 17.
Assistant: 25 plus 17 equals 42.
User: Second, explain what photosynthesis is.
Assistant: Photosynthesis is the process plants use to convert sunlight into energy.
User: That’s helpful.
Assistant: Anything else you’d like to ask?
User: No, that covers both questions.
Assistant: Happy to help!""",
    "scenario_07_noisy": """User: Uh hi… I was like trying to um… check something about weather maybe tomorrow?
Assistant: It sounds like you're asking about tomorrow’s weather.
User: Yeah yeah… like rain maybe… not sure…
Assistant: Could you tell me which city you’re asking about?
User: Bangalore… sorry typing fast.
Assistant: No problem. I can help check the forecast.
User: I just want to know if I should carry an umbrella.
Assistant: If rain is predicted, carrying an umbrella is a good idea.
User: Okay that helps.
Assistant: Glad I could assist.""",
    "scenario_08_owner_in_text": """User: The project document mentions that Ravi is the owner.
Assistant: That means Ravi is responsible for managing the project.
User: Does the owner approve changes?
Assistant: Usually yes, the owner reviews and approves updates.
User: Should I contact him for clarification?
Assistant: Yes, contacting the owner is recommended.
User: The document says “Owner: Ravi Kumar.”
Assistant: That clearly identifies the responsible person.
User: I’ll reach out to him.
Assistant: Good idea."""
}
