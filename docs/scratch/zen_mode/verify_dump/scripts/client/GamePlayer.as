package client
{
   public class GamePlayer
   {
      
      public var id:int;
      
      public var isBot:Boolean;
      
      public var displayName:String;
      
      public var country:String;
      
      public var picture:String;
      
      public var cosmeticInfo:Object;
      
      public var badges:Array;
      
      public var ping:int;
      
      public var avatarFrame:String;
      
      public function GamePlayer(playerInfo:Object)
      {
         super();
         this.id = playerInfo.id;
         this.isBot = playerInfo.bot != "";
         this.displayName = playerInfo.displayName;
         this.picture = playerInfo.portrait;
         if(this.picture == "")
         {
            this.picture = "empty";
         }
         this.ping = NaN;
         this.country = "";
         this.cosmeticInfo = playerInfo.cosmetics;
         this.badges = playerInfo.trophies;
         this.avatarFrame = playerInfo.avatarFrame;
         if(Profile.proxy != null && this.id != Profile.proxy.myID && !this.isBot)
         {
            this.displayName = "";
            this.picture = "empty";
            this.badges = [];
            this.avatarFrame = null;
         }
      }
   }
}

