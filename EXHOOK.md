andyshinn — 5/14/25, 3:08 PM
@Ask Inkeep i want to only all certain messages to be published to subscribers. are any of the extensions or hooks able to let me filter what messages coming in can or can not be sent back out to subscribers?
Ask Inkeep
APP
 — 5/14/25, 3:08 PM
Thanks for tagging me @andyshinn. I'll look through relevant sources and get back to you shortly.
Answer
Yes, you can use EMQX hooks to filter messages before they are published to subscribers. The message.publish hook point allows you to intercept messages before they are published (1)  .

There are two main ways to implement this:

Using an Erlang plugin:
You can create a plugin that sets headers = #{allow_publish := false} in the message to prevent it from being published (2)  .

Using ExHook (for other programming languages) :
For Java implementations, you can create a message object with the allow_publish header set to false to prevent publication (3)  . Here's an example in Java:

Message message = Message.newBuilder()
    .putHeaders("allow_publish", "false")
    .build() ;
ValuedResponse response = ValuedResponse.newBuilder()
    .setType(ValuedResponse.ResponsedType.STOP_AND_RETURN)
    .setMessage(message)
    .build() ;



For plugins extending EMQX functionality, they can currently only be written in Erlang (4)  . However, you can use ExProto Gateway to create external applications in other programming languages that connect to EMQX via gRPC .
​
To learn more, see the sources I considered:

[1] Hooks
[2] EMQX Plugin on Message Publish | How to stop it from being published
[3] Java extension hook publishes message even when creating a ValuedResponse with STOP_AND_RETURN
[4] Extension/plugins for Signature validation
​
Image
GitHub
EMQX Plugin on Message Publish | How to stop it from being publishe...
Hi guys, I&#39;ve been trying to create my first EMQX Plugin, to validate the messages being published and reject the ones that don&#39;t follow a particular pattern. The Erlang code seems to be do...
Hi guys, I've been trying to create my first EMQX Plugin, to validate the messages being published and reject the ones that don't follow a particular pattern. The Erlang code seems to be doing what...
GitHub
Java extension hook publishes message even when creating a ValuedRe...
What happened? I am writing a topic rate limiter. On a topic you can specify how much time must elapse before the next message is accepted. Therefore I override public void onMessagePublish(Message...
What happened? I am writing a topic rate limiter. On a topic you can specify how much time must elapse before the next message is accepted. Therefore I override public void onMessagePublish(Message...
GitHub
Extension/plugins for Signature validation · emqx emqx · Discussi...
Hi guys, recently we have been looking to see how we could implement a custom signature validation on incoming messages; but we are not sure if we understood correctly how the Plugins / Extensions ...
Feel free to tag @Ask Inkeep with additional questions. I also appreciate feedback, it helps me improve.
andyshinn — 5/14/25, 3:09 PM
is it possible to do when i don't control the message itself? i wouldn't be able to set headers on the message at the client
@Ask Inkeep is it possible to do when i don't control the message itself? i wouldn't be able to set headers on the message at the client
Ask Inkeep
APP
 — 5/14/25, 3:10 PM
Thanks for the follow-up, @andyshinn. I'll get back to you soon.
Answer
Yes, you can filter messages without modifying the client-side message. There are two main approaches:

Using the message transformation feature which allows you to modify and format messages based on user-defined rules before they are processed or delivered to subscribers (1)  .

Using hooks to intercept the message.publish event, which occurs before the server publishes (routes) the message (2)  . The hook handler can examine the message properties including:
topic
payload
QoS
clientid
username
(3)

For example, in Java you can create a hook response that prevents message publishing by setting the header on the server-side, without modifying the original message:

Message message = Message.newBuilder()
    .putHeaders("allow_publish", "false")
    .build() ;
ValuedResponse response = ValuedResponse.newBuilder()
    .setType(ValuedResponse.ResponsedType.STOP_AND_RETURN)
    .setMessage(message)
    .build() ;

(4)

This allows you to implement filtering logic on the server without requiring any changes to the client messages.
​
To learn more, see the sources I considered:

[1] Message Transformation
[2] Hooks
[3] Data Sources and Fields
[4] Java extension hook publishes message even when creating a ValuedResponse with STOP_AND_RETURN
​
Image
Image
Image
GitHub
Java extension hook publishes message even when creating a ValuedRe...
What happened? I am writing a topic rate limiter. On a topic you can specify how much time must elapse before the next message is accepted. Therefore I override public void onMessagePublish(Message...
What happened? I am writing a topic rate limiter. On a topic you can specify how much time must elapse before the next message is accepted. Therefore I override public void onMessagePublish(Message...
Feel free to tag @Ask Inkeep with additional questions. I also appreciate feedback, it helps me improve.
andyshinn — 5/14/25, 3:12 PM
@Ask Inkeep can server side hooks be done in python instead of java?
Ask Inkeep
APP
 — 5/14/25, 3:12 PM
Thanks for the follow-up, @andyshinn. I'll get back to you soon.
Answer
Yes, you can implement server-side hooks in Python. EMQX supports using gRPC as the communication framework for implementing hooks in other programming languages through the ExHook feature (1)  .

The steps to implement hooks in Python would be:

Copy the exhook.proto file from EMQX to your project
Generate the gRPC server code from the proto file using Python's gRPC framework
Implement the HookProvider service interfaces defined in the proto file

EMQX provides example implementations for various programming languages in their emqx-extension-examples repository .

Once implemented, you can manage and monitor your Python ExHook service through the EMQX Dashboard .
​
To learn more, see the sources I considered:

[1] gRPC Hook Extension
​
Image
Feel free to tag @Ask Inkeep with additional questions. I also appreciate feedback, it helps me improve.
andyshinn — 5/14/25, 3:50 PM
@Ask Inkeep i would do HTTP instead of gRPC. can i do a HTTP ExHook to filter messages instead?
Ask Inkeep
APP
 — 5/14/25, 3:50 PM
Thanks for the follow-up, @andyshinn. I'll get back to you soon.
Answer
Based on the available documentation, ExHook specifically uses gRPC as its communication framework (1)  . There is no mention of HTTP support for ExHook in the documentation. The ExHook plugin is designed to work with gRPC for processing EMQX hooks .

If you prefer to work with HTTP, you may want to explore other EMQX extension options or consider using the gRPC implementation, which is the supported method for extending EMQX hooks.
​
To learn more, see the sources I considered:

[1] gRPC Hook Extension
​
Image
Feel free to tag @Ask Inkeep with additional questions. I also appreciate feedback, it helps me improve.
