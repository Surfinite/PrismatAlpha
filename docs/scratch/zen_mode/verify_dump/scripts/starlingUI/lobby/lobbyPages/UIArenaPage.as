package starlingUI.lobby.lobbyPages
{
   import client.Client;
   import client.Collection;
   import client.GoogleAnalytics;
   import client.LocalUser;
   import client.NetworkEvent;
   import client.Profile;
   import client.Progression;
   import flash.external.ExternalInterface;
   import flash.utils.getTimer;
   import mcds.Util;
   import mx.utils.StringUtil;
   import sound.SoundManager;
   import starling.display.DisplayObject;
   import starling.display.Quad;
   import starling.events.Event;
   import starling.filters.BlurFilter;
   import starling.utils.HAlign;
   import starlingUI.Align;
   import starlingUI.Animate;
   import starlingUI.Palette;
   import starlingUI.RomanNumerals;
   import starlingUI.UIContainer;
   import starlingUI.UIEvent;
   import starlingUI.UIImage;
   import starlingUI.UILabel;
   import starlingUI.UIYesNoPopup;
   import starlingUI.asset.CommonAssets;
   import starlingUI.asset.FontAsset;
   import starlingUI.asset.LobbyAsset;
   import starlingUI.asset.MenuAsset;
   import starlingUI.controls.Hovertip;
   import starlingUI.controls.UIHoverToolTip;
   import starlingUI.controls.UIProgressBar;
   import starlingUI.controls.buttons.ButtonFactory;
   import starlingUI.controls.buttons.UICleanButton;
   import starlingUI.lobby.arena.UIArenaTicket;
   import starlingUI.lobby.arena.UIArenaTicketInventoryModal;
   import starlingUI.lobby.arena.UISupporterIcon;
   import starlingUI.lobby.arena.UIprizeScreen;
   import starlingUI.lobby.collection.badges.Badge;
   import starlingUI.lobby.effect.TierFlare;
   import starlingUI.lobby.homepage.UINewbiePopup;
   import starlingUI.lobby.lobbyStructure.UILobbyPage;
   import starlingUI.lobby.lobbyStructure.UILobbyTabs;
   import starlingUI.lobby.multiplayer.UIArenaModal;
   import starlingUI.lobby.multiplayer.UIAutomatchSettings;
   
   public class UIArenaPage extends UILobbyPage
   {
      
      public static var magicFindValue:Number = 0;
      
      public static const RANKED_LEVEL_THRESHOLD:int = 20;
      
      private const w:int = 622;
      
      private const h:int = 432;
      
      private const spacing:int = 10;
      
      private const PLAY:String = "";
      
      private const CASUALMATCHING:String = "Click to Cancel\nEvent Match..." + "DOES THIS EVEN GET USED";
      
      private const TEXT_PENALTY_WARNING:String = "Your true $5Master Rating$0 is {0}, but you have been\nassigned a temporary $5Vacation Penalty$0 of {1} points for\nnot playing enough ranked games in the last two weeks.\nPlay another {2} ranked games to remove this penalty.";
      
      private var page:UIContainer;
      
      private var settingsBtn:UICleanButton;
      
      private var retireBtn:UICleanButton;
      
      private var playBtn:UIArenaTicket;
      
      private var streakLabel:UILabel;
      
      private var streakIcon:UISupporterIcon;
      
      private var arenaYesNo:UIYesNoPopup;
      
      private var arenaYesNo2:UIYesNoPopup;
      
      private var addArenaWin:UICleanButton;
      
      private var addArenaLoss:UICleanButton;
      
      private var tierFlare:DisplayObject;
      
      private var tierEmblem:UIImage;
      
      private var tierLabel:UILabel;
      
      private var tierLabelRating:UILabel;
      
      private var tierPenaltyTip:UIHoverToolTip;
      
      private var tierProgressBar:UIProgressBar;
      
      private var bonusLeftFlare:DisplayObject;
      
      private var bonusLeftBottomFlare:DisplayObject;
      
      private var bonusRightFlare:DisplayObject;
      
      private var bonusInfoLeft:UIContainer;
      
      private var bonusInfoLeftBottom:UIContainer;
      
      private var bonusInfoRight:UIContainer;
      
      public var bonus_platticket:UISupporterIcon;
      
      public var bonus_goldenpass:UISupporterIcon;
      
      private var bonus_supporter:UISupporterIcon;
      
      private var bonus_collector:UISupporterIcon;
      
      private var arenaTicketInventory:UICleanButton;
      
      private var arenaTicketInventoryIcon:UIImage;
      
      private var goldenPassIconTooltip:UIHoverToolTip;
      
      private var initTime:Number;
      
      private var rankedLock:UIImage;
      
      private var glowfilter:BlurFilter = BlurFilter.createGlow(Palette.green);
      
      public function UIArenaPage()
      {
         super(true);
      }
      
      override protected function buildComponents() : void
      {
         var supporter_icon_count_visible:int;
         var startx:int;
         var starty:int;
         var c:Collection;
         var bonuses:Array;
         var v1:int;
         var v2:int;
         var i:int;
         var i2:int;
         var TEXT_RANKED_TIP:String;
         var fString:String;
         var canPlayRanked:Boolean;
         var q:Quad;
         var obj:DisplayObject = null;
         var _q:UIImage = null;
         var rankedLockoutScreen:UIContainer = null;
         var _ticketImage:UIArenaTicket = null;
         var _img:UIImage = null;
         var _lbl:UILabel = null;
         var dx:Number = NaN;
         var dy:Number = NaN;
         addChild(this.page = new UIContainer(5,4));
         this.page.addChild(obj = new Quad(this.w,this.h - 20,0));
         obj.alpha = 0;
         this.playBtn = new UIArenaTicket((this.w - UIArenaTicket.w) / 2,20,0,this.PLAY,this.playCallback);
         addChild(this.playBtn);
         this.settingsBtn = ButtonFactory.cleanButton(this.w / 2 - 80,this.h - 60,100,48,this.settingsCallback);
         this.settingsBtn.alignPivot();
         addChild(this.settingsBtn);
         this.settingsBtn.setIcon(new UIImage(0,0,LobbyAsset.getTexture(LobbyAsset.OTHER + "arena_settings_icon")));
         this.retireBtn = ButtonFactory.cleanButton(this.w / 2 + 80,this.h - 60,100,48,this.retireCallback);
         this.retireBtn.alignPivot();
         addChild(this.retireBtn);
         this.retireBtn.setIcon(new UIImage(0,0,LobbyAsset.getTexture(LobbyAsset.OTHER + "retireTorn")),10);
         this.page.addChild(this.streakIcon = new UISupporterIcon(130,130,UISupporterIcon.TYPE_STREAK,"",new UILabel("",0,-5,{
            "size":20,
            "hAlign":HAlign.CENTER,
            "font":FontAsset.EXO_BOLD
         })));
         this.streakIcon.mlabel.dropShadowFilter.strength = 2;
         this.streakIcon.mlabel.dropShadowFilter.distance = 0;
         this.streakIcon.mlabel.dropShadowFilter.blurX = 6;
         this.streakIcon.mlabel.dropShadowFilter.blurY = 6;
         this.streakIcon.visible = false;
         this.page.addChild(this.addArenaWin = ButtonFactory.cleanButton(this.w,5,24,24,function():void
         {
            Client.sayToServer(NetworkEvent.SERVER_SENDCHATCOMMAND,"addArenaWin");
         },"+"));
         this.page.addChild(this.addArenaLoss = ButtonFactory.cleanButton(this.w,30,24,24,function():void
         {
            Client.sayToServer(NetworkEvent.SERVER_SENDCHATCOMMAND,"addArenaLoss");
         },"+"));
         this.addArenaWin.visible = this.addArenaLoss.visible = false;
         supporter_icon_count_visible = 0;
         startx = 280;
         starty = this.h - 65;
         this.bonus_platticket = new UISupporterIcon(startx,starty,UISupporterIcon.TYPE_PLATTICKET,"",new UILabel(TR("10/wk"),-10,0,{
            "width":40,
            "hAlign":HAlign.RIGHT,
            "font":FontAsset.EXO_BOLD,
            "size":"10"
         }));
         this.bonus_goldenpass = new UISupporterIcon(startx,starty,UISupporterIcon.TYPE_GOLDENPASS,"");
         this.bonus_supporter = new UISupporterIcon(startx,starty,UISupporterIcon.TYPE_SUPPORTER,"");
         this.bonus_collector = new UISupporterIcon(startx,starty,UISupporterIcon.TYPE_COLLECTOR,"");
         this.bonus_platticket.visible = this.bonus_goldenpass.visible = this.bonus_supporter.visible = this.bonus_collector.visible = false;
         this.page.addChild(this.bonus_platticket);
         this.page.addChild(this.bonus_goldenpass);
         this.page.addChild(this.bonus_supporter);
         this.page.addChild(this.bonus_collector);
         c = Collection.proxy;
         if(c.arenaTickets[1] == null)
         {
            this.bonus_goldenpass.visible = true;
            supporter_icon_count_visible++;
         }
         if(c.supporterBonus)
         {
            this.bonus_supporter.visible = true;
            supporter_icon_count_visible++;
         }
         if(c.collectorBonus)
         {
            this.bonus_collector.visible = true;
            supporter_icon_count_visible++;
         }
         if(Boolean(c.weeklyGiveaway) && "arenaTickets" in c.weeklyGiveaway)
         {
            this.bonus_platticket.visible = true;
            this.bonus_platticket.mlabel.text = String(c.weeklyGiveaway["arenaTickets"][2]) + "/wk";
            supporter_icon_count_visible++;
         }
         if(FlashBuildOptions.developerVersion)
         {
            this.bonus_platticket.visible = this.bonus_goldenpass.visible = this.bonus_supporter.visible = this.bonus_collector.visible = true;
            supporter_icon_count_visible = 4;
         }
         this.settingsBtn.x -= 20 * supporter_icon_count_visible;
         this.retireBtn.x += 20 * supporter_icon_count_visible;
         this.arenaTicketInventory = ButtonFactory.cleanButton(102,300,50,30,this.openArenaTicketInventory);
         this.arenaTicketInventory.iconGlow = true;
         this.arenaTicketInventory.enabledTooltipText = TR("Ticket Inventory");
         this.arenaTicketInventory.setIcon(new UIImage(0,0,LobbyAsset.getTexture(LobbyAsset.ARENA + "arenainventoryicon")),-5);
         this.arenaTicketInventory.toolTipAlignment = Align.TOP;
         this.arenaTicketInventory.visible = true;
         this.page.addChild(this.arenaTicketInventory);
         if(Collection.proxy.arenaTickets[1] != null && Collection.proxy.arenaTickets[1].length > 0 || Collection.proxy.arenaTickets[2] != null && Collection.proxy.arenaTickets[2].length > 0)
         {
            this.arenaTicketInventory.visible = true;
         }
         this.initTime = new Date().valueOf() - getTimer();
         this.updatePlatTooltip();
         bonuses = [this.bonus_collector,this.bonus_platticket,this.bonus_goldenpass,this.bonus_supporter];
         v1 = 0;
         v2 = 0;
         i = 0;
         while(i < 4)
         {
            if(bonuses[i].visible)
            {
               v1 += 1;
            }
            i++;
         }
         v2 = int(v1);
         i2 = 0;
         while(i2 < 4)
         {
            if(bonuses[i2].visible)
            {
               bonuses[i2].x += 50 * v1 - 25 * v2;
               v1--;
            }
            i2++;
         }
         addChild(_q = new UIImage(476,310,MenuAsset.getTexture("question_mark")));
         _q.scale = 0.5;
         TEXT_RANKED_TIP = TR("Prismata has ten $3Ranked Play Tiers$0:\n • Earn progress by winning Ranked Play games.\n • Reach 100% progress to advance to the next tier.\n • You cannot lose progress until reaching Tier III.\n • Reach Tier X to receive a $5Master Rating$0.");
         addChild(new Hovertip(_q,TEXT_RANKED_TIP,null,{
            "offsetX":-int(_q.x),
            "offsetY":-int(_q.y),
            "isHtmlText":true,
            "hAlign":HAlign.LEFT
         }));
         addChild(this.tierFlare = new TierFlare(this.w / 2,this.h / 2 - 10));
         addChild(this.tierEmblem = new UIImage(this.w / 2,this.h / 2 - 10,LobbyAsset.getTexture(LobbyAsset.TIER_EMBLEMS + "Tier_" + Client.localUser.myTier)));
         this.tierEmblem.scale = 0.8;
         this.tierEmblem.alignPivot();
         fString = TR("Tier {0}");
         addChild(this.tierLabel = new UILabel(Client.localUser.myTier == 10 ? TR("Master") : StringUtil.substitute(fString,RomanNumerals.toRomanNumerals(Client.localUser.myTier)),this.w / 4,this.h / 2 + 45,{
            "size":20,
            "hAlign":HAlign.CENTER,
            "width":this.w / 2,
            "font":FontAsset.EXO_BOLD
         }));
         addChild(this.tierLabelRating = new UILabel("9999",this.w / 4,this.h / 2 + 80,{
            "size":16,
            "hAlign":HAlign.CENTER,
            "width":this.w / 2
         }));
         addChild(this.tierPenaltyTip = new UIHoverToolTip(0,0,this.ratingPenaltyWarning(),this.tierLabelRating,"",this.w / 4,this.h / 2 + 80,true,false));
         this.tierPenaltyTip.tooltip.setLabelOptions({"isHtmlText":true});
         this.tierProgressBar = new UIProgressBar((this.w - 266) / 2,this.h / 2 + 90,"arenaTierProgress");
         this.tierProgressBar.alignPivot();
         this.tierProgressBar.paddingH = this.tierProgressBar.paddingV = 6;
         this.tierProgressBar.backgroundSkin = new UIImage(0,0,LobbyAsset.getTexture(LobbyAsset.ARENA + "tierBar"));
         this.tierProgressBar.backgroundSkin.scaleY = 1.05;
         this.tierProgressBar.fillSkin = new Quad(0.0001,100,Palette.tier_fill);
         this.tierProgressBar.fillSkin.scaleY = 1.4;
         addChild(this.tierProgressBar);
         addEventListener(Event.ENTER_FRAME,this.updatePlatTooltip);
         Client.localUser.addEventListener(LocalUser.EVENT_AUTOMATCHER_UPDATED,this.updatePlayBtn);
         UIEvent.listen(UIEvent.LEADERBOARD_UPDATED,this.updateTierLabels);
         UIEvent.listen(UIEvent.ARENA_UPDATED,this.updateArena);
         UIEvent.listen(UIEvent.COLLECTION_UPDATED,this.updateArena);
         addChild(rankedLockoutScreen = new UIContainer());
         canPlayRanked = Badge.MULTIPLAYER_Prismata_Tier_I.currentCount > 0;
         rankedLockoutScreen.addChild(_ticketImage = new UIArenaTicket(185 + 25,130 + 10,0));
         _ticketImage.noText();
         _ticketImage.touchable = false;
         _ticketImage.alpha = 0.8;
         _ticketImage.scaleX = _ticketImage.scaleY = 0.8;
         rankedLockoutScreen.addChild(this.rankedLock = new UIImage(310,200,CommonAssets.getTexture(CommonAssets.MISC + "lock")));
         this.rankedLock.alignPivot();
         this.rankedLock.scale = 0.5;
         this.rankedLock.touchable = false;
         Animate.toggleGlow(this.rankedLock);
         q = new Quad(_ticketImage.width * _ticketImage.scaleX,_ticketImage.height * _ticketImage.scaleY);
         q.alpha = 0;
         q.x = _ticketImage.x;
         q.y = _ticketImage.y;
         rankedLockoutScreen.addChild(q);
         fString = TR("Unlock Ranked Play by reaching Level {0},\nor by achieving a streak of 3 consecutive honorable Master Bot victories.");
         addChild(new Hovertip(q,StringUtil.substitute(fString,String(RANKED_LEVEL_THRESHOLD)),null,{
            "align":Align.BOTTOM,
            "offsetX":-210,
            "offsetY":-140
         }));
         i = 1;
         while(i < 11)
         {
            dx = Math.sin(Math.PI * i / 5.5) * -150;
            dy = Math.cos(Math.PI * i / 5.5) * 150;
            rankedLockoutScreen.addChild(_img = new UIImage(310 + dx,200 + dy,LobbyAsset.getTexture(LobbyAsset.TIER_EMBLEMS + "Tier_" + i)));
            _img.alpha = 0.8;
            _img.scale = 0.5;
            _img.alignPivot();
            i++;
         }
         if(!canPlayRanked)
         {
            this.page.visible = this.playBtn.visible = this.settingsBtn.visible = this.retireBtn.visible = _q.visible = false;
            this.tierFlare.visible = this.tierEmblem.visible = this.tierLabel.visible = this.tierPenaltyTip.visible = this.tierProgressBar.visible = false;
            this.streakIcon.visible = false;
            rankedLockoutScreen.visible = true;
         }
         else
         {
            Progression.proxy.showNew_Ranked = false;
            UIEvent.say(UILobbyTabs.EVENT_REMOVE_NEW_GRAPHIC_BATTLE);
            if(Progression.proxy.level < 40 && !Progression.proxy.rankedWarningAgreed)
            {
               UINewbiePopup.create(UINewbiePopup.TYPE_RANKED);
            }
            this.page.visible = this.playBtn.visible = this.settingsBtn.visible = this.retireBtn.visible = _q.visible = true;
            this.tierFlare.visible = this.tierEmblem.visible = this.tierLabel.visible = this.tierPenaltyTip.visible = this.tierProgressBar.visible = true;
            this.streakIcon.visible = false;
            this.updateStreakIcon();
            rankedLockoutScreen.visible = false;
         }
         this.updateArena();
         this.updateTierLabels();
      }
      
      private function ratingPenaltyWarning() : String
      {
         return StringUtil.substitute(TR(this.TEXT_PENALTY_WARNING),String(int(Math.round(Client.localUser.myScore))),String(int(Math.round(Client.localUser.myScoreWithPenalty - Client.localUser.myScore))),String(Client.localUser.myNumberOfGamesToRemovePenalty));
      }
      
      override protected function removed() : void
      {
         if(this.rankedLock)
         {
            Animate.toggleGlow(this.rankedLock,false);
         }
         super.removed();
         removeEventListener(Event.ENTER_FRAME,this.updatePlatTooltip);
         if(Client.localUser)
         {
            Client.localUser.removeEventListener(LocalUser.EVENT_AUTOMATCHER_UPDATED,this.updatePlayBtn);
         }
         UIEvent.stopListening(UIEvent.LEADERBOARD_UPDATED,this.updateTierLabels);
         UIEvent.stopListening(UIEvent.ARENA_UPDATED,this.updateArena);
         UIEvent.stopListening(UIEvent.COLLECTION_UPDATED,this.updateArena);
      }
      
      private function automatch() : void
      {
         GoogleAnalytics.trackEvent(GoogleAnalytics.CATEGORY_LOBBY,"Queued on automatch");
         GoogleAnalytics.beginTrackTime("automatch");
         Client.localUser.automatch(LocalUser.AUTOMATCHQ_RANKED);
         if(ExternalInterface.available)
         {
            ExternalInterface.call("Notification.requestPermission");
         }
      }
      
      private function settingsCallback() : void
      {
         new UIAutomatchSettings();
      }
      
      private function retireCallback() : void
      {
         var cb:Function = this.retire;
         if(Profile.proxy.arenaType > 1 || Profile.proxy.arenaType == 1 && Collection.proxy.arenaTickets[1] != null)
         {
            cb = this.retireCallbackSecondConfirm;
         }
         this.arenaYesNo = new UIYesNoPopup(TR("Abandon your current Ranked Play ticket and start over?"),cb);
      }
      
      private function retireCallbackSecondConfirm() : void
      {
         var fString:String = TR("You have a {ticket} in progress, do you really want to retire?");
         fString = TRN(fString,"ticket",Profile.proxy.arenaType == 1 ? "Golden Ticket" : "Platinum Ticket");
         this.arenaYesNo2 = new UIYesNoPopup(fString,this.retire);
      }
      
      private function retire() : void
      {
         if(this.arenaYesNo)
         {
            this.arenaYesNo.removeFromParent();
            this.arenaYesNo = null;
         }
         if(this.arenaYesNo2)
         {
            this.arenaYesNo2.removeFromParent();
            this.arenaYesNo2 = null;
         }
         Profile.proxy.arenaType = -1;
         Profile.proxy.arenaWins = 0;
         this.updateArena();
         Client.sayToServer("stopArena");
         Client.localUser.automatchCancel(LocalUser.AUTOMATCHQ_RANKED);
         this.playBtn.validateButton();
      }
      
      private function playCallback() : void
      {
         if(Profile.proxy.arenaType == -1)
         {
            new UIArenaModal();
            SoundManager.playSound("SFX_BUTTON_CLICK");
         }
         else
         {
            SoundManager.playSound("SFX_ARENA_ENQ");
            this.automatch();
         }
      }
      
      private function updatePlayBtn() : void
      {
         if(Client.localUser.automatchQstatus[LocalUser.AUTOMATCHQ_RANKED])
         {
            this.playBtn.setText(false);
            this.playBtn.text = TR("Automatching...\n(Click to Cancel)");
            this.playBtn.callback = function():void
            {
               SoundManager.playSound("SFX_ARENA_UNENQ");
               Client.localUser.automatchCancel(LocalUser.AUTOMATCHQ_RANKED);
            };
         }
         else if(Collection.proxy && Collection.proxy.arenaRewards && Collection.proxy.arenaRewards.length > 0)
         {
            if(UIprizeScreen.active)
            {
               this.playBtn.setText(false);
               this.playBtn.text = "";
               this.playBtn.callback = function():void
               {
               };
            }
            else
            {
               this.playBtn.setText(false);
               this.playBtn.text = TR("CLAIM REWARDS");
               this.playBtn.callback = function():void
               {
                  if(!Profile.proxy.lastArenaScoreData)
                  {
                     new UIprizeScreen();
                  }
                  else
                  {
                     new UIprizeScreen(Profile.proxy.lastArenaScoreData);
                  }
               };
            }
         }
         else if(Profile.proxy.arenaType != -1)
         {
            this.playBtn.text = this.PLAY;
            this.playBtn.setText(true);
            this.playBtn.callback = this.playCallback;
         }
         else
         {
            this.playBtn.validateButton();
            this.playBtn.text = this.PLAY;
            this.playBtn.setText(true);
            this.playBtn.callback = this.playCallback;
         }
      }
      
      private function updateStreakIcon() : void
      {
         if(Collection.proxy.streakLength > 2)
         {
            if(Collection.proxy.streakLength >= 5)
            {
               Badge.MULTIPLAYER_Hot_Streak.incrementCount();
            }
            if(Collection.proxy.streakLength >= 8)
            {
               Badge.MULTIPLAYER_Unstoppable.incrementCount();
            }
            if(Collection.proxy.streakLength >= 10)
            {
               Badge.MULTIPLAYER_Legendary.incrementCount();
            }
            this.streakIcon.visible = true;
            Animate.toggleGlow(this.streakIcon.icon);
            if(this.streakIcon.mlabel)
            {
               this.streakIcon.mlabel.text = "" + Collection.proxy.streakLength;
               this.streakIcon.hovertip.text = StringUtil.substitute(TR("You are on a streak of {0} consecutive wins"),Collection.proxy.streakLength);
            }
         }
         else
         {
            this.streakIcon.visible = false;
            Animate.toggleGlow(this.streakIcon.icon,false);
         }
      }
      
      private function updateArena() : void
      {
         if(Profile.proxy.arenaType == -1)
         {
            this.addArenaWin.visible = this.addArenaLoss.visible = false;
            this.retireBtn.enabled = false;
            this.playBtn.ticketType = UIArenaTicket.types[0];
         }
         else
         {
            if(FlashBuildOptions.developerVersion)
            {
               this.addArenaWin.visible = this.addArenaLoss.visible = true;
            }
            this.retireBtn.enabled = true;
            this.updateStreakIcon();
            this.playBtn.ticketType = UIArenaTicket.types[Profile.proxy.arenaType];
         }
         this.updatePlayBtn();
         this.playBtn.setStrikes();
         this.updateStreakIcon();
         if(Profile.proxy.justCompletedArena)
         {
            if(Collection.proxy && Collection.proxy.arenaRewards && Collection.proxy.arenaRewards.length > 0)
            {
               new UIprizeScreen(Profile.proxy.justCompletedArenaScore);
            }
            Profile.proxy.justCompletedArena = false;
            Client.localUser.automatchCancel();
         }
      }
      
      private function updateTierLabels() : void
      {
         this.tierLabelRating.text = "";
         this.tierLabelRating.visible = false;
         this.tierLabelRating.touchable = false;
         if(Client.localUser.myTier == 10)
         {
            this.tierProgressBar.visible = false;
         }
         else
         {
            this.tierProgressBar.setProgress(Client.localUser.myTierPercent);
         }
      }
      
      private function updatePlatTooltip() : void
      {
         var genText:String = Util.secondsToTime(604800 + (1386287940 - int((this.initTime + getTimer()) / 1000)) % 604800);
         var fString:String = TR("You receive free $8Platinum Tickets$0 every week.\nTickets are generated on Thursdays at 11:59 PM UTC.\nTime until tickets are generated: {0}");
         this.bonus_platticket.hovertip.text = StringUtil.substitute(fString,genText);
      }
      
      private function openArenaTicketInventory() : void
      {
         new UIArenaTicketInventoryModal();
      }
   }
}

