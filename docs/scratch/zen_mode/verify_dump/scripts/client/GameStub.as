package client
{
   import flash.utils.getTimer;
   
   public class GameStub
   {
      
      public var gameid:String;
      
      public var players:Array;
      
      public var ratings:Array;
      
      public var tiers:Array;
      
      public var tierpcts:Array;
      
      public var started:int;
      
      public var lastupdated:int;
      
      public var timeControl:String;
      
      public var deckName:String;
      
      public var units:Array;
      
      public function GameStub(serverObject:Object)
      {
         var pName:String = null;
         super();
         for(pName in serverObject)
         {
            this[pName] = serverObject[pName];
         }
         this.lastupdated = getTimer();
         this.players = ["?","?"];
      }
      
      public static function compare(a:GameStub, b:GameStub) : int
      {
         if(a.score > b.score)
         {
            return -1;
         }
         if(a.score < b.score)
         {
            return 1;
         }
         return 0;
      }
      
      public function get score() : Number
      {
         var s:Number = (this.ratings[0] + this.ratings[1]) / 2;
         return s - 100 * this.started / (1000 * 60);
      }
      
      public function ratingstring(i:int) : String
      {
         return "";
      }
   }
}

