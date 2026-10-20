The goal of this project is to create a drum practice app. The core functionality is to provide the user a beat and assess the accuracy of their playback.

## The app does the following:
- play a beat out loud for you and show you the notes. when they're being played, a note should be lit up or have some other visual indicator on it that it's being played.
- then you play it back and it gives you a grade/% based on your accuracy. On playback, the beat should still be visible on the screen and have the visual indicator of when it should be being played but this time theres no sound.
- i think that it should be n bars at a time where n is set by the user
- beats can be begineer/intermediate/advanced, again something the user picks
- beats can be of some set of genres that the user picks
## The drumset to test against
- I have a basic electric yamaha kit. It has a port (not real midi but usb-b) and I can connect to my laptop with a usbB-usbA wire. It is currently connected. Important: make sure you can see the connection before we begin!
## Advanced Requirements
- It would also be nice for the user to be able to add/edit beats themselves like a drag and drop sheet music thing
- Or be able to upload sheet music for a whole song so they're scored against it - we would need a way to encode a regular sheet to our ap
## Tech stack
- In terms of the tech stack, I'm not sure what makes the most sense. It could be local. Maybe Java or Python? Something fast and easy and not overkill. But keep in mind it does need a decent looking modern GUI.
## On building process
We should build in phases and test between each, so make the plan accordingly. For example, maybe we start by just having an app (with gui or even just cli-based) that only has one beat. It plays it for the user and judges its accuracy 
## Drum beats data
- Instead of populating drumbeat data alone, we could source an existing dataset of copyright free/public domain music. It's important to not use any proprietary data here. 


