

Next steps
- Rebuild clearcase history from a given date
- Support passing custom configuration file to bridgerunner.py
- Meaningful tests
- Make the bridge run continuously as a process
- Checkin to clearcase from a specific branch to enable proof build to be run before syncing
- Support for specifying branches to sync with

A word on testing
Testing bare-git-cc appears to be a bit tricky. I had one approach to record all calls (and returns) to the cc and git facades respectively, and then just verify a replay, but since also the file system (calls to os.path.exists mainly) affects the bridge behavior this didn't work out. I would have to create another abstraction for the FS, and that didn't feel like the obvious choice. But maybe it's the only way.
