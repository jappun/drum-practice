We have built out phase 7. After testing, the plan needs to be changed. 

With this new information, create REVISION1_PLAN_PHASES.md which will be the new source of truth for the build. It may affect phase 8, but phase 9 and 10 should remain unchanged. The new plan file should say which phases from PLAN_PHASES.md were completed + are being kept, which are being removed, and which are being put into the revision plan (eg phase 9)

# Revisions:

## Feedback: 
- I don't like the Groove Midi dataset, as we've simplified it. It would be better off if it's fully user created/uploaded beats.
- The accent color should be purple (#8742f5) instead of orange
- Being stuck to a 16th grid is no good. Drumbeats have so much variation. Perhaps the UI should look more like actual sheet music (see `docs/rock-beats.png`), but keep a "grid view" option.

## New Requirements:
- I want to be able to upload just a drumbeat. Use case: I have a book full of beats that I want to practice. I could take a picture of that bar and then it'll be encoded into my app. Jpeg/jpg and png handling is good. 
- the last core function is still a full song upload. music XML is good for now. 
- Because the library is user-generated, the filters aren't really as important now. Instead we should have a library for drumbeats (searchable by name) and for songs (also searchable).
- If beats are long and go off screen (which will be the case for full songs), I'm wondering if a slow slide into screen is any good. Kind of like guitar hero vibes where the notes sldie in for you. 
- Speaking of a "drum hero" mode would actually be a really fun way to gamify this I think that ultimately to put it concisely I'm re-building guitar hero but for drums and to actually teach you 

