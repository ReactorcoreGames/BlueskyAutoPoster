# 🌊 Automated Bluesky Poster 🤖

> Post to Bluesky automatically on a schedule, without leaving your bed! No coding knowledge required! 

## ✨ What is this?

This is a simple tool that automatically posts content to your Bluesky account on a schedule. Just fill in a spreadsheet with your posts, set it up once, and it will handle the rest!

- 🕒 Posts automatically every 12 hours
- 📝 Cycles through your list of prepared posts
- 🔄 Works completely on its own after setup
- 🔗 Properly formats your links to be clickable
- 📱 No need to open Bluesky or remember to post

## 🚀 Quick Setup Guide

### Step 1: Copy this repository 📋

1. Click the **Fork** button at the top right of this page
2. Name your new repository whatever you want (like "my-bluesky-poster")
3. Click **Create fork**

Congrats! Now you have your own copy of this tool! 🎉

### Step 2: Prepare your posts 📝

1. In your new repository, find the `posts.csv` file and click on it
2. Click the **pencil icon** (Edit this file)
3. Add your posts in the format: 
   ```
   title,url,hashtags
   Check out my cool project!,https://example.com,#cool #project #awesome
   ```
4. Each row will become one post
5. Click **Commit changes** when done

### Step 3: Get your Bluesky app password 🔑

1. Log in to your Bluesky account
2. Go to Settings → App Passwords
3. Create a new app password (name it "GitHub Poster" or something you'll remember)
4. Copy the password immediately (you won't see it again!)

### Step 4: Add your Bluesky info to GitHub 🔒

1. In your GitHub repository, click on **Settings**
2. In the left sidebar, click on **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Create a secret named `BLUESKY_HANDLE` with your username (like `yourusername.bsky.social`)
5. Create another secret named `BLUESKY_APP_PASSWORD` with the app password you copied

### Step 5: Start the poster! 🎬

1. Click on the **Actions** tab in your repository
2. Click on **Bluesky Poster** in the left sidebar
3. Click the **Run workflow** button
4. Click the green **Run workflow** button in the popup

Woohoo! 🎉 Your first post will be sent immediately, and then it will continue posting every 12 hours!

## 📊 How to check if it's working

1. Go to the **Actions** tab in your repository
2. Look for green checkmarks ✅ next to "Bluesky Poster" runs
3. Click on any run to see the details
4. Check your Bluesky profile to see your posts!

## 🛠️ Customizing your posting schedule

Want to post more or less frequently? You can change the schedule by editing the `.github/workflows/poster.yml` file:

1. Click on the file and then the edit (pencil) icon
2. Find the line that says `cron: '0 */12 * * *'`
3. Change it to:
   - Every 6 hours: `0 */6 * * *`
   - Once a day: `0 12 * * *` (posts at 12:00 UTC)
   - Twice a day on weekdays only: `0 9,17 * * 1-5`

## 🤔 Troubleshooting

**Posts not showing up?**
- Check the Actions tab for any red ❌ errors
- Make sure your Bluesky handle and app password are correct
- Verify your posts.csv file has the correct format

**Need to pause posting?**
- Go to Settings → Actions → General
- Scroll down and select "Disable Actions"

## 🌟 Tips and Tricks

- 💡 Keep URLs short to leave more room for your message
- 💡 Use hashtags strategically to reach more people
- 💡 Mix up your content to keep followers engaged
- 💡 You can manually trigger posts anytime from the Actions tab

## 📞 Need help?

Open an issue in this repository if you get stuck, and someone might be able to help you out!

---

Happy posting! 🌊✨
