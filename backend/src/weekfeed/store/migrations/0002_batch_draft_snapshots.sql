-- The draft's sections just before and just after a drafting-chat turn, so Undo can put the text back.
ALTER TABLE agent_batches ADD COLUMN draft_before TEXT;
ALTER TABLE agent_batches ADD COLUMN draft_after TEXT;
