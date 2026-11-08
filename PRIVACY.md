# Privacy Policy

**Effective Date:** October 2026  
**Application:** Social Clip Engine / ClipForge Studio (YouTube Clip Pipeline)  
**Maintained by:** Kushagra Singh Negi (<kushagra910200@gmail.com>)  

---

### 1. Overview
Social Clip Engine ("the Application") is an internal content management and automated short-form video publishing pipeline designed to discover, format, and publish video shorts to YouTube channels owned and operated by the channel administrator.

The Application uses **YouTube API Services** to automate video uploads, video metadata management, and publication scheduling.

### 2. Adherence to YouTube Terms of Service and Google Privacy Policy
By using this Application or authorizing access via Google OAuth, you acknowledge and agree that:
- This application uses YouTube API Services.
- Users are bound by the [YouTube Terms of Service](https://www.youtube.com/t/terms).
- Google collects and processes user data in accordance with the [Google Privacy Policy](https://policies.google.com/privacy).

### 3. What Data We Access, Collect, and Store
- **Authorized YouTube Account Information:** When granting OAuth access, the Application requests authorization under the `https://www.googleapis.com/auth/youtube.upload` scope.
- **Tokens:** The Application stores encrypted OAuth 2.0 refresh tokens inside secure GitHub Actions secrets. These tokens are used solely to authenticate API calls to upload video clips and retrieve upload statuses.
- **No Third-Party Sharing:** The Application does not sell, rent, monetize, or transfer user information or YouTube account credentials to any third party or advertising service.
- **No Personal Data Harvesting:** The Application does not collect viewer personal information, email contacts, or search histories.

### 4. Data Retention and Deletion
- OAuth credentials and channel tokens are retained only as long as necessary to facilitate scheduled uploads for the designated YouTube channel.
- If an authorized channel is removed from the pipeline, its associated credentials and tokens are immediately deleted.

### 5. Revocation of Access
Users and channel owners may revoke the Application's access to their YouTube data at any time via the Google Security Settings page:
👉 [https://security.google.com/settings/security/permissions](https://security.google.com/settings/security/permissions)

Revoking access immediately invalidates the stored refresh token and terminates all automated API interactions.

### 6. Contact Information
For questions regarding this privacy policy or API usage, please contact:
- **Email:** kushagra910200@gmail.com
- **Repository:** https://github.com/Kushagra001/youtube-clip-pipeline
