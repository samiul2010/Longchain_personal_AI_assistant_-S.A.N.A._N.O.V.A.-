import gradio as gr

gr.load(
   "models/google/gemma-4-31B-it",
   provider="novita",
).launch()