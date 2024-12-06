from statemachine import StateMachine, State


# class TrafficLightStateMachine(StateMachine):

    # red = State(initial=True)

    # write_to_upstream_connection = State()

    # flush_downstream_to_upstream_buffer = State()



    # green = State()

    # cycle = red.to(orange) | orange.to(green) | green.to(red)




def test_fsm():
    pass

    # sm = TrafficLightStateMachine()
    
    # while True:
    #     sm.send("cycle")
    #     s = sm.current_state
    #     print(s.id)