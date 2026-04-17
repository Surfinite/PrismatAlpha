package starlingUI.splash.components
{
   import client.Ario;
   import client.Auth;
   import client.Client;
   import client.GoogleAnalytics;
   import client.NetworkEvent;
   import client.Steamworks;
   import flash.external.ExternalInterface;
   import sound.SoundManager;
   import starling.display.Image;
   import starlingUI.Align;
   import starlingUI.Key;
   import starlingUI.KeyEvent;
   import starlingUI.PaddedContainer;
   import starlingUI.UIErrorPopup;
   import starlingUI.UIEvent;
   import starlingUI.UIForgotPasswordPopup;
   import starlingUI.UIImage;
   import starlingUI.UILabel;
   import starlingUI.UIOfflinePopup;
   import starlingUI.UIPanel;
   import starlingUI.UIScreen;
   import starlingUI.asset.EmbeddedAssets;
   import starlingUI.asset.FontAsset;
   import starlingUI.asset.LobbyAsset;
   import starlingUI.controls.UICheckbox;
   import starlingUI.controls.buttons.ButtonFactory;
   import starlingUI.controls.buttons.ButtonTextures;
   import starlingUI.controls.buttons.TCButton;
   import starlingUI.controls.feathersControls.UITextInput;
   import starlingUI.splash.UISteamRegisterPopup;
   import starlingUI.splash.components.customButtons.SignUpButton;
   
   public class LogInMenu extends SplashComponent
   {
      
      private var mPanel:UIPanel;
      
      private var mUsernameEmailInput:UITextInput;
      
      private var mPasswordInput:UITextInput;
      
      private var mFacebookButton:SignUpButton;
      
      private var mGoogleButton:SignUpButton;
      
      private var mSteamButton:TCButton;
      
      private var mSignUpButtonContainer:PaddedContainer;
      
      private var mSignUpButtonSpacing:int = 5;
      
      private var mLogInButtonSize:Number = 0.6;
      
      private var mLogInButton:TCButton;
      
      private var mForgotButton:TCButton;
      
      private var mRememberMeCheckbox:UICheckbox;
      
      private var mOrCutout:Image;
      
      private var mOrLabel:UILabel;
      
      private var mOfflineButton:TCButton;
      
      private const steamOffset:int = 10;
      
      public function LogInMenu()
      {
         vPadding = UIPanel.BORDER_SIZE + Align.SPACING.VERTICAL;
         hPadding = UIPanel.BORDER_SIZE + Align.SPACING.HORIZONTAL;
         super();
         width = SplashComponentManager.LOGIN_MENU_WIDTH;
         height = SplashComponentManager.LOGIN_MENU_HEIGHT;
         if(!Ario.isReady())
         {
            height += 20;
         }
         if(Steamworks.isReady)
         {
            height += this.steamOffset;
         }
         else
         {
            height -= 80;
         }
      }
      
      override protected function buildComponents() : void
      {
         this.mPanel = new UIPanel();
         addChild(this.mPanel);
         this.mUsernameEmailInput = new UITextInput();
         this.mUsernameEmailInput.icon = UITextInput.ICON_PERSON;
         this.mUsernameEmailInput.prompt = TR("Username or Email");
         this.mUsernameEmailInput.maxChars = UITextInput.TYPICAL_MAX_CHARACTERS;
         this.mUsernameEmailInput.restrict = "a-zA-Z0-9\\-.\'!?()[]_@#$%&*+/={|}~`";
         this.mUsernameEmailInput.onChangeCallback = this.loginButtonSwitch;
         this.mPasswordInput = new UITextInput();
         this.mPasswordInput.icon = UITextInput.ICON_KEY;
         this.mPasswordInput.displayAsPassword = true;
         this.mPasswordInput.prompt = TR("Password");
         this.mPasswordInput.maxChars = UITextInput.TYPICAL_MAX_CHARACTERS;
         this.mPasswordInput.onChangeCallback = this.loginButtonSwitch;
         this.mUsernameEmailInput.nextTabFocus = this.mPasswordInput;
         this.mPasswordInput.nextTabFocus = this.mUsernameEmailInput;
         this.mUsernameEmailInput.isRootFocusObject = true;
         addChild(this.mUsernameEmailInput);
         addChild(this.mPasswordInput);
         this.mLogInButton = new TCButton(ButtonTextures.login());
         this.mLogInButton.callback = this.tryLogInRegular;
         this.mLogInButton.setLabelFormat(TR("LOG IN"),FontAsset.EXO_BOLD,30);
         this.mLogInButton.clickSoundName = null;
         this.mLogInButton.disable();
         addChild(this.mLogInButton);
         this.mFacebookButton = new SignUpButton(SignUpButton.TYPE_FACEBOOK,SignUpButton.STYLE_LOGIN);
         this.mGoogleButton = new SignUpButton(SignUpButton.TYPE_GOOGLE,SignUpButton.STYLE_LOGIN);
         this.mSteamButton = new TCButton(new ButtonTextures(new UIImage(0,0,EmbeddedAssets.steamLoginBD,false,true,0.55555),new UIImage(0,0,EmbeddedAssets.steamLoginHoverBD,false,true,0.55555)));
         this.mSignUpButtonContainer = new PaddedContainer();
         this.mFacebookButton.button.callback = this.login_Facebook;
         this.mGoogleButton.button.callback = this.login_Google;
         this.mSteamButton.callback = this.loginSteam;
         if(Steamworks.isReady)
         {
            addChild(this.mSignUpButtonContainer);
            this.mSignUpButtonContainer.addChild(this.mSteamButton);
         }
         if(!Ario.isReady())
         {
            this.mOfflineButton = ButtonFactory.cleanButton(0,0,paddedWidth * 0.52,30,this.playOffline);
            this.mOfflineButton.setLabelFormat(TR("Play in Airplane Mode"),FontAsset.EXO_MEDIUM,16);
            this.mOfflineButton.disabledTooltipText = TR("Play offline vs AI (campaigns require DLC)");
            addChild(this.mOfflineButton);
         }
         this.mForgotButton = ButtonFactory.cleanButton(0,0,paddedWidth * 0.75,30,this.forgotDetails);
         this.mForgotButton.setLabelFormat(TR("Forgot Username or Password"),FontAsset.EXO_MEDIUM,16);
         addChild(this.mForgotButton);
         this.mRememberMeCheckbox = new UICheckbox(0,0);
         this.mRememberMeCheckbox.labelText = TR("Remember Me");
         this.mRememberMeCheckbox.callback = this.toggleRememberMe;
         this.mRememberMeCheckbox.checked = Client.rememberMe;
         addChild(this.mRememberMeCheckbox);
         this.mOrCutout = new Image(LobbyAsset.getTexture(LobbyAsset.SOCIAL_MEDIA + "circular_or_cutout"));
         this.mOrLabel = new UILabel(TR("OR"),0,0);
         this.mOrLabel.fontSize = 14;
         this.mOrLabel.fontName = FontAsset.EXO_BOLD;
         if(Steamworks.isReady)
         {
            addChild(this.mOrLabel);
         }
         UIEvent.listen("Log In Error Exit",this.errorCallback);
      }
      
      override protected function removed() : void
      {
         UIEvent.stopListening("Log In Error Exit",this.errorCallback);
         super.removed();
      }
      
      override protected function positionComponents() : void
      {
         var internal_vertical_spacing:int = 5;
         this.mPanel.width = width;
         this.mPanel.height = height;
         this.mSignUpButtonContainer.width = paddedWidth;
         this.mSignUpButtonContainer.height = 80;
         this.mGoogleButton.width = this.mFacebookButton.width = Math.round((this.paddedWidth - this.mSignUpButtonSpacing) / 2);
         this.mFacebookButton.height = this.mGoogleButton.height = this.mSignUpButtonContainer.height;
         this.mGoogleButton.x = this.mFacebookButton.bounds.right + this.mSignUpButtonSpacing;
         this.mSteamButton.x = 23;
         this.mSteamButton.y = 36;
         this.mSignUpButtonContainer.x = hPadding;
         this.mSignUpButtonContainer.y = vPadding;
         if(Steamworks.isReady)
         {
            this.mPanel.y = this.steamOffset;
         }
         this.mOrCutout.alignPivot();
         Align.pivotCenter(this.mOrLabel);
         Align.fitWithin(this.mOrCutout,30,30,0);
         Align.centreHorizontal(this.mOrLabel,this);
         Align.centreHorizontal(this.mOrCutout,this);
         this.mOrLabel.y = this.mOrCutout.y = this.mSignUpButtonContainer.bounds.bottom;
         this.mUsernameEmailInput.width = this.mPasswordInput.width = this.paddedWidth;
         this.mUsernameEmailInput.height = this.mPasswordInput.height = SplashComponentManager.TEXT_INPUT_HEIGHT;
         this.mUsernameEmailInput.x = this.mPasswordInput.x = this.hPadding;
         if(Steamworks.isReady)
         {
            this.mUsernameEmailInput.y = this.mOrLabel.bounds.bottom + internal_vertical_spacing;
         }
         else
         {
            this.mUsernameEmailInput.y = this.mSignUpButtonContainer.y;
         }
         this.mPasswordInput.y = this.mUsernameEmailInput.bounds.bottom + internal_vertical_spacing * 2;
         this.mLogInButton.width = paddedWidth * this.mLogInButtonSize;
         this.mLogInButton.height = 64;
         Align.centreHorizontal(this.mLogInButton,this);
         this.mLogInButton.y = this.mPasswordInput.bounds.bottom + internal_vertical_spacing * 4;
         this.mRememberMeCheckbox.width = this.mLogInButton.width * 0.8;
         this.mRememberMeCheckbox.height = 30;
         Align.centreHorizontal(this.mRememberMeCheckbox,this);
         this.mRememberMeCheckbox.y = this.mLogInButton.bounds.bottom + internal_vertical_spacing;
         this.mForgotButton.labelHPadding = 6;
         Align.centreHorizontal(this.mForgotButton,this);
         this.mForgotButton.y = height - vPadding - this.mForgotButton.height;
         if(this.mOfflineButton)
         {
            this.mOfflineButton.labelHPadding = 6;
            Align.centreHorizontal(this.mOfflineButton,this);
            this.mOfflineButton.y = height - vPadding - this.mOfflineButton.height;
            this.mForgotButton.y = this.mOfflineButton.bounds.top - vPadding - this.mForgotButton.height;
         }
         if(Steamworks.isReady)
         {
            this.mForgotButton.y += this.steamOffset;
            this.mOfflineButton.y += this.steamOffset;
         }
      }
      
      private function forgotDetails() : void
      {
         new UIForgotPasswordPopup();
      }
      
      private function playOffline() : void
      {
         new UIOfflinePopup();
      }
      
      private function loginButtonSwitch() : void
      {
         if(this.mUsernameEmailInput.text != "" && this.mPasswordInput.text != "")
         {
            this.mLogInButton.enable();
         }
         else
         {
            this.mLogInButton.disable();
         }
      }
      
      private function loginSteam() : void
      {
         SoundManager.playSound("SFX_BUTTON_CONFIRM");
         new UISteamRegisterPopup(true);
      }
      
      private function tryLogInRegular() : void
      {
         SoundManager.playSound("SFX_BUTTON_CONFIRM");
         var allFieldsValid:Boolean = true;
         if(this.mUsernameEmailInput.text == "")
         {
            this.mUsernameEmailInput.indicator.displayError(TR("Username or Email cannot be blank."));
            allFieldsValid = false;
         }
         if(this.mPasswordInput.text == "" && (!FlashBuildOptions.developerVersion || !allFieldsValid))
         {
            this.mPasswordInput.indicator.displayError(TR("Password cannot be blank."));
            allFieldsValid = false;
         }
         if(allFieldsValid)
         {
            isFocus = false;
            this.login_UsernamePassword();
         }
      }
      
      private function clearInput() : void
      {
         this.mUsernameEmailInput.indicator.displayError("");
         this.mPasswordInput.indicator.displayError("");
      }
      
      private function errorCallback() : void
      {
         isFocus = true;
      }
      
      private function toggleRememberMe(value:Boolean) : void
      {
         Client.rememberMe = value;
      }
      
      private function login_Facebook() : void
      {
         if(!ExternalInterface.available || !FlashBuildOptions.enableFacebookLogin)
         {
            new UIErrorPopup(TR("Facebook login is currently disabled."));
            return;
         }
         GoogleAnalytics.trackEvent(GoogleAnalytics.CATEGORY_ACCOUNT,"Logging in with Facebook");
         Auth.requestFBAuth(function(signedRequest:String, accessToken:String):void
         {
            Client.tryLogInFB(signedRequest,accessToken);
         });
      }
      
      private function login_Google() : void
      {
         if(!ExternalInterface.available || !FlashBuildOptions.enableGoogleLogin)
         {
            new UIErrorPopup(TR("Google login is currently disabled."));
            return;
         }
         GoogleAnalytics.trackEvent(GoogleAnalytics.CATEGORY_ACCOUNT,"Logging in with Google");
         Auth.requestGoogleAuth(function(idToken:String):void
         {
            Client.tryLogInGoogle(idToken);
         });
      }
      
      private function login_UsernamePassword() : void
      {
         Client.listenToSecureServer(NetworkEvent.SERVER_SECURE_PASSWORD_SALT,Client.loginSalt);
         Client.tryLogInPassword(this.mUsernameEmailInput.text,this.mPasswordInput.text);
      }
      
      override protected function onFocusChange(focus:Boolean) : void
      {
         if(focus)
         {
            this.mUsernameEmailInput.setFocus();
            this.mUsernameEmailInput.isRootFocusObject = true;
            KeyEvent.listenJustPressed(Key.ENTER,this.tryLogInRegular,null,true);
         }
         else
         {
            this.mUsernameEmailInput.clearFocus();
            this.mUsernameEmailInput.isRootFocusObject = false;
            KeyEvent.stopListeningJustPressed(Key.ENTER,this.tryLogInRegular,null,true);
         }
      }
      
      override protected function onProgressChange() : void
      {
         this.x = SplashComponentManager.SCREEN_EDGE_PADDING - UIScreen.WIDTH * (1 - progressState);
         if(Steamworks.isReady)
         {
            this.y = UIScreen.HEIGHT - SplashComponentManager.SCREEN_EDGE_PADDING - height;
         }
         else
         {
            this.y = UIScreen.HEIGHT - SplashComponentManager.SCREEN_EDGE_PADDING - height - 30;
         }
      }
      
      override protected function onScreenChange() : void
      {
         this.visible = isOnScreen;
         if(isOnScreen)
         {
            Client.clientDispatcher.addEventListener(Client.EVENT_LOGIN_ERROR,this.clearInput);
            Client.clientDispatcher.addEventListener(Client.EVENT_LOGIN_SUCCESSFUL,this.clearInput);
         }
         else
         {
            Client.clientDispatcher.removeEventListener(Client.EVENT_LOGIN_ERROR,this.clearInput);
            Client.clientDispatcher.removeEventListener(Client.EVENT_LOGIN_SUCCESSFUL,this.clearInput);
         }
      }
      
      override protected function onReset() : void
      {
         if(this.mUsernameEmailInput)
         {
            this.mUsernameEmailInput.text = Client.autoLoginName;
            this.mUsernameEmailInput.indicator.hide();
         }
         if(this.mPasswordInput)
         {
            this.mPasswordInput.text = "";
            this.mPasswordInput.indicator.hide();
         }
      }
   }
}

