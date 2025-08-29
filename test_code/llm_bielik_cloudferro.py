import llm

# https://llm.datasette.io/en/stable/python-api.html

# print(llm.get_models())

model = llm.get_model("bielik")

resp = model.prompt("Jak się nazywasz?")

print(print(resp.text()))
